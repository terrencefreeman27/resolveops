"""Human review and execution: edit, approve, reject, retry.

Backend-enforced rules:
- Nothing touches tickets until an approval row exists for the exact proposal version + action hash.
- Approving anything but the current version, or with a mismatched action hash, fails.
- Editing creates a new version and invalidates any previous approval.
- The request row is locked (SELECT ... FOR UPDATE) for approve/edit/retry, so concurrent
  clicks serialize; executions and tickets carry a UNIQUE idempotency key as a backstop.
- Execution retries are bounded; every attempt and failure is audited.
"""
import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit
from .adapters.base import ExecutionTarget
from .adapters.internal import get_adapter
from .config import get_settings
from .models import Approval, Execution, Proposal, ProposalVersion, SupportRequest, Workspace
from .schemas import ApproveIn, EditProposalIn, ProposalContent, RejectIn
from .tools import ToolError, call_tool
from .workflow import RESOLUTION, tool_context, transition, save_version


class ReviewError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def idempotency_key(pv: ProposalVersion) -> str:
    return hashlib.sha256(f"{pv.id}:{pv.action_hash}".encode()).hexdigest()


def lock_request(db: Session, req_id) -> SupportRequest:
    req = db.scalar(select(SupportRequest).where(SupportRequest.id == req_id).with_for_update())
    if req is None:
        raise ReviewError("Request not found.", 404)
    return req


def current(db: Session, req: SupportRequest) -> tuple[Proposal, ProposalVersion]:
    proposal = db.scalar(select(Proposal).where(Proposal.request_id == req.id, Proposal.status != "closed")
                         .order_by(Proposal.created_at.desc()).limit(1))
    if proposal is None:
        raise ReviewError("This request has no open proposal.")
    pv = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id,
                                                 ProposalVersion.version == proposal.current_version))
    return proposal, pv


def _audit(db, req, actor, event, **kw):
    audit.record(db, workspace_id=req.workspace_id, actor=actor, event=event, request_id=req.id,
                 demo_session_id=req.demo_session_id, **kw)


def _refuse_if_stale(db: Session, req: SupportRequest, what: str) -> None:
    if req.state != "stale":
        return
    p = db.scalar(select(Proposal).where(Proposal.request_id == req.id, Proposal.status == "stale")
                  .order_by(Proposal.created_at.desc()).limit(1))
    reason = p.stale_reason if p is not None else "its evidence changed"
    raise ReviewError(f"Cannot {what}: this proposal is stale. {reason} Reprocess it against current "
                      "documentation to get a new version; nothing was executed.")


def edit(db: Session, req_id, actor: str, body: EditProposalIn) -> ProposalVersion:
    req = lock_request(db, req_id)
    _refuse_if_stale(db, req, "edit")
    if req.state not in ("awaiting_review", "failed"):
        raise ReviewError(f"Proposals can only be edited while awaiting review or after a failed execution (state: {req.state}).")
    proposal, pv = current(db, req)
    if body.base_version != proposal.current_version:
        raise ReviewError(f"Edit is based on v{body.base_version} but the current version is v{proposal.current_version}. Reload and try again.")
    content = ProposalContent.model_validate(pv.content)
    changed = []
    for field in ("draft_reply", "next_action", "ticket_action"):
        value = getattr(body, field)
        if value is not None and value != getattr(content, field):
            setattr(content, field, value)
            changed.append(field)
    if not changed:
        raise ReviewError("No changes to save.", 422)
    ec = content.evidence_check
    if "next_action" in changed and content.next_action == "resolve" and ec is not None and ec.status != "sufficient":
        raise ReviewError(f"Evidence for this request is {ec.status}; it cannot be resolved with a confident answer. "
                          "Fix the documentation, then reprocess.", 422)
    try:
        checked = call_tool(tool_context(db, req, actor), "propose_ticket_action",
                            content.ticket_action.model_dump(mode="json"))
    except ToolError as exc:
        raise ReviewError(str(exc), 422) from exc
    if not checked.valid:
        db.commit()  # keep the audit record of the rejected edit
        raise ReviewError("Ticket action is invalid: " + "; ".join(checked.problems), 422)
    new_pv = save_version(db, proposal, proposal.current_version + 1, content, actor,
                          edit_note=body.note, evidence_from=pv)
    invalidated = db.query(Approval).filter(Approval.proposal_id == proposal.id, Approval.status == "active").update(
        {"status": "invalidated", "invalidated_reason": f"Proposal edited to v{new_pv.version}"})
    transition(db, req, "awaiting_review", actor, f"Edited to v{new_pv.version}; needs approval")
    _audit(db, req, actor, "proposal.edited", summary={"version": new_pv.version, "changed": changed,
                                                       "approvals_invalidated": invalidated, "note": body.note})
    db.commit()
    return new_pv


def reject(db: Session, req_id, actor: str, body: RejectIn) -> SupportRequest:
    req = lock_request(db, req_id)
    _refuse_if_stale(db, req, "reject")
    if req.state != "awaiting_review":
        raise ReviewError(f"Only proposals awaiting review can be rejected (state: {req.state}).")
    proposal, pv = current(db, req)
    if body.proposal_version_id != pv.id:
        raise ReviewError("Rejection refers to an outdated proposal version.")
    db.add(Approval(workspace_id=req.workspace_id, request_id=req.id, proposal_id=proposal.id,
                    proposal_version_id=pv.id, action_hash=pv.action_hash, decision="rejected",
                    actor=actor, reason=body.reason))
    proposal.status = "closed"
    transition(db, req, "rejected", actor, body.reason)
    _audit(db, req, actor, "approval.rejected", summary={"version": pv.version, "reason": body.reason})
    db.commit()
    return req


def approve(db: Session, req_id, actor: str, body: ApproveIn) -> SupportRequest:
    req = lock_request(db, req_id)
    _refuse_if_stale(db, req, "approve")
    if req.state != "awaiting_review":
        raise ReviewError(f"Request is not awaiting review (state: {req.state}); nothing was executed.")
    proposal, pv = current(db, req)
    if proposal.status == "stale":
        raise ReviewError("Proposal relies on superseded documentation; reprocess it first.")
    if body.proposal_version_id != pv.id:
        raise ReviewError(f"Approval is for an outdated proposal version; current is v{pv.version}.")
    if body.action_hash != pv.action_hash:
        raise ReviewError("Action hash does not match the current proposal version.")
    approval = Approval(workspace_id=req.workspace_id, request_id=req.id, proposal_id=proposal.id,
                        proposal_version_id=pv.id, action_hash=pv.action_hash, decision="approved", actor=actor)
    db.add(approval)
    try:
        db.flush()
    except IntegrityError as exc:  # one active approval per proposal
        db.rollback()
        raise ReviewError("This proposal already has an active approval.") from exc
    transition(db, req, "approved", actor, f"v{pv.version} approved")
    _audit(db, req, actor, "approval.granted", summary={"version": pv.version, "action_hash": pv.action_hash[:12]})
    content = ProposalContent.model_validate(pv.content)
    ex = Execution(workspace_id=req.workspace_id, demo_session_id=req.demo_session_id, request_id=req.id,
                   proposal_version_id=pv.id, approval_id=approval.id, idempotency_key=idempotency_key(pv),
                   adapter=_adapter_name(db, req), action_type=content.ticket_action.type, status="pending")
    db.add(ex)
    transition(db, req, "executing", actor)
    db.commit()  # approval + execution intent are durable before any side effect
    return _run_execution(db, req.id, ex.id, actor)


def retry(db: Session, req_id, actor: str) -> SupportRequest:
    req = lock_request(db, req_id)
    _refuse_if_stale(db, req, "retry execution")
    if req.state != "failed":
        raise ReviewError(f"Only failed executions can be retried (state: {req.state}).")
    proposal, pv = current(db, req)
    approval = db.scalar(select(Approval).where(Approval.proposal_id == proposal.id, Approval.status == "active",
                                                Approval.decision == "approved", Approval.proposal_version_id == pv.id))
    if approval is None:
        raise ReviewError("No valid approval for the current version; approve it again.")
    ex = db.scalar(select(Execution).where(Execution.idempotency_key == idempotency_key(pv)))
    if ex is None or ex.status == "succeeded":
        raise ReviewError("Nothing to retry.")
    ex.status = "pending"
    transition(db, req, "executing", actor, "Retry")
    _audit(db, req, actor, "execution.retry", summary={"execution_id": str(ex.id)})
    db.commit()
    return _run_execution(db, req.id, ex.id, actor)


def _adapter_name(db: Session, req: SupportRequest) -> str:
    if req.demo_session_id is not None:
        return "internal"  # visitor sandboxes never reach external integrations
    return db.get(Workspace, req.workspace_id).settings.get("ticket_adapter", "internal")


def _run_execution(db: Session, req_id, ex_id, actor: str) -> SupportRequest:
    settings = get_settings()
    req = lock_request(db, req_id)
    ex = db.get(Execution, ex_id)
    pv = db.get(ProposalVersion, ex.proposal_version_id)
    proposal = db.get(Proposal, pv.proposal_id)
    if proposal.status == "stale":  # defensive: invalidation and execution both lock the request row
        raise ReviewError("Proposal became stale before execution; nothing was executed.")
    content = ProposalContent.model_validate(pv.content)
    action = content.ticket_action
    target = ExecutionTarget(req.workspace_id, req.demo_session_id, req.customer_id, req.id, content.category)
    result, error = None, None
    for _ in range(settings.execution_max_attempts):
        ex.attempts += 1
        started = time.perf_counter()
        try:
            with db.begin_nested():  # savepoint: a failed attempt leaves no partial writes
                db.execute(_timeout_sql(settings.execution_attempt_timeout_s))
                if action.type == "create_ticket":
                    result = get_adapter(ex.adapter).create_ticket(db, target, action, ex.idempotency_key)
                elif action.type == "add_note":
                    result = get_adapter(ex.adapter).add_note(db, target, action, ex.idempotency_key)
            _audit(db, req, actor, "execution.attempt", tool_name=f"adapter.{ex.adapter}",
                   duration_ms=int((time.perf_counter() - started) * 1000),
                   summary={"attempt": ex.attempts, "action": action.type,
                            "ticket": result.number if result else None,
                            "created": result.created if result else None})
            error = None
            break
        except Exception as exc:  # noqa: BLE001 - every failure is recorded and bounded
            error = str(exc)
            _audit(db, req, actor, "execution.attempt", tool_name=f"adapter.{ex.adapter}",
                   duration_ms=int((time.perf_counter() - started) * 1000),
                   summary={"attempt": ex.attempts, "action": action.type}, error=error)
    ex.finished_at = datetime.now(timezone.utc)
    if error is None:
        ex.status, ex.last_error = "succeeded", None
        ex.ticket_id = result.ticket_id if result else None
        req.resolution = RESOLUTION[content.next_action]
        proposal.status = "closed"
        note = (f"Ticket {result.number} {'created' if action.type == 'create_ticket' else 'updated'}"
                if result else "No ticket change; reply draft approved (drafts are not sent in v1)")
        transition(db, req, "completed", actor, note)
        _audit(db, req, actor, "execution.succeeded", summary={"execution_id": str(ex.id), "result": note,
                                                               "resolution": req.resolution})
    else:
        ex.status, ex.last_error = "failed", error
        transition(db, req, "failed", actor, f"Execution failed after {ex.attempts} attempt(s): {error}")
        _audit(db, req, actor, "execution.failed", summary={"execution_id": str(ex.id), "attempts": ex.attempts},
               error=error)
    db.commit()
    return req


def _timeout_sql(seconds: float):
    return text(f"SET LOCAL statement_timeout = {int(seconds * 1000)}")
