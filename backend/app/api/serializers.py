"""Shape DB rows into API responses. Scoping is applied by the callers (see api/requests.py)."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..context import Actor, scope_clause
from ..models import (AiRun, Approval, AuditLog, Customer, Document, DocumentVersion, Execution, Proposal,
                      ProposalVersion, SupportRequest, Ticket)


def iso(dt):
    return dt.isoformat() if dt else None


def citation_status(db: Session, version_ids) -> dict:
    """document_version_id -> {status, current_version, document_status} for cited versions."""
    if not version_ids:
        return {}
    cur = DocumentVersion.__table__.alias("cur")
    rows = db.execute(
        select(DocumentVersion.id, DocumentVersion.status, Document.status, cur.c.version)
        .join(Document, Document.id == DocumentVersion.document_id)
        .outerjoin(cur, cur.c.id == Document.current_version_id)
        .where(DocumentVersion.id.in_(list(version_ids)))).all()
    return {vid: {"status": st, "document_status": dst, "current_version": cv} for vid, st, dst, cv in rows}


def request_summary(r: SupportRequest, customer: Customer | None) -> dict:
    return {
        "id": str(r.id), "subject": r.subject, "from_name": r.from_name, "from_email": r.from_email,
        "state": r.state, "state_reason": r.state_reason, "category": r.category, "priority": r.priority,
        "resolution": r.resolution, "scenario_key": r.scenario_key, "is_template": r.is_template,
        "source_request_id": str(r.source_request_id) if r.source_request_id else None,
        "received_at": iso(r.received_at), "updated_at": iso(r.updated_at),
        "customer": None if customer is None else {
            "id": str(customer.id), "company_name": customer.company_name, "account_ref": customer.account_ref,
            "is_synthetic": customer.is_synthetic},
    }


def ticket_dict(t: Ticket) -> dict:
    return {"id": str(t.id), "number": t.number, "subject": t.subject, "body": t.body, "category": t.category,
            "priority": t.priority, "status": t.status, "group": t.group, "source": t.source, "adapter": t.adapter,
            "notes": t.notes, "sandbox": t.demo_session_id is not None, "created_at": iso(t.created_at),
            "request_id": str(t.request_id) if t.request_id else None}


def allowed_actions(r: SupportRequest, has_proposal: bool) -> dict:
    return {
        "run": r.is_template or r.state in ("received", "rejected", "stale", "error", "unsupported"),
        "edit": not r.is_template and has_proposal and r.state in ("awaiting_review", "failed"),
        "approve": not r.is_template and has_proposal and r.state == "awaiting_review",
        "reject": not r.is_template and has_proposal and r.state == "awaiting_review",
        "retry": not r.is_template and r.state == "failed",
    }


def request_detail(db: Session, actor: Actor, r: SupportRequest) -> dict:
    customer = db.get(Customer, r.customer_id) if r.customer_id else None
    out = request_summary(r, customer)
    out["body"] = r.body
    proposal = db.scalar(select(Proposal).where(Proposal.request_id == r.id).order_by(Proposal.created_at.desc()).limit(1))
    out["proposal"] = None
    if proposal is not None:
        versions = db.scalars(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                              .order_by(ProposalVersion.version)).all()
        cur = next(v for v in versions if v.version == proposal.current_version)
        cited = {c["document_version_id"] for c in cur.content.get("citations", [])}
        statuses = citation_status(db, [uuid.UUID(x) for x in cited])
        out["proposal"] = {
            "id": str(proposal.id), "provider": proposal.provider, "status": proposal.status, "usage": proposal.usage,
            "stale_reason": proposal.stale_reason, "stale_at": iso(proposal.stale_at),
            "citation_versions": {str(k): v for k, v in statuses.items()},
            "current_version": proposal.current_version,
            "version": {"id": str(cur.id), "version": cur.version, "content": cur.content,
                        "action_hash": cur.action_hash, "author": cur.author, "edit_note": cur.edit_note,
                        "created_at": iso(cur.created_at)},
            "versions": [{"id": str(v.id), "version": v.version, "author": v.author, "edit_note": v.edit_note,
                          "created_at": iso(v.created_at)} for v in versions],
        }
    out["approvals"] = [
        {"id": str(a.id), "decision": a.decision, "actor": a.actor, "status": a.status, "reason": a.reason,
         "invalidated_reason": a.invalidated_reason, "version_id": str(a.proposal_version_id),
         "created_at": iso(a.created_at)}
        for a in db.scalars(select(Approval).where(Approval.request_id == r.id).order_by(Approval.created_at))]
    out["executions"] = [
        {"id": str(e.id), "status": e.status, "attempts": e.attempts, "last_error": e.last_error,
         "adapter": e.adapter, "action_type": e.action_type, "idempotency_key": e.idempotency_key[:12],
         "ticket_id": str(e.ticket_id) if e.ticket_id else None, "created_at": iso(e.created_at),
         "finished_at": iso(e.finished_at)}
        for e in db.scalars(select(Execution).where(Execution.request_id == r.id).order_by(Execution.created_at))]
    out["tickets"] = [ticket_dict(t) for t in db.scalars(
        select(Ticket).where(Ticket.request_id == r.id, scope_clause(actor, Ticket)).order_by(Ticket.created_at))]
    out["timeline"] = [
        {"id": a.id, "event": a.event, "actor": a.actor, "tool_name": a.tool_name, "summary": a.summary,
         "duration_ms": a.duration_ms, "error": a.error, "created_at": iso(a.created_at)}
        for a in db.scalars(select(AuditLog).where(AuditLog.request_id == r.id).order_by(AuditLog.id))]
    out["ai_runs"] = [
        {"id": str(x.id), "provider": x.provider, "model": x.model, "status": x.status, "latency_ms": x.latency_ms,
         "input_tokens": x.input_tokens, "output_tokens": x.output_tokens, "tool_steps": x.tool_steps,
         "api_calls": x.api_calls, "error": x.error, "created_at": iso(x.created_at)}
        for x in db.scalars(select(AiRun).where(AiRun.request_id == r.id).order_by(AiRun.created_at))]
    out["allowed_actions"] = allowed_actions(r, proposal is not None and proposal.status != "closed")
    return out


def visible_requests_clause(actor: Actor):
    """Templates (shared seeded inbox, read-only) plus rows in the caller's own scope."""
    return (SupportRequest.workspace_id == actor.workspace_id) & or_(
        SupportRequest.is_template.is_(True),
        (SupportRequest.is_template.is_(False)) & scope_clause(actor, SupportRequest))
