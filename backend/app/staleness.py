"""Stale-evidence invalidation (SPEC §9: policy changes invalidate pending proposals).

A proposal is *pending* while its request is `awaiting_review` (not yet approved) or `failed`
(approved, execution not completed). When evidence it relied on changes, the proposal is marked
`stale` **inside the caller's transaction** — the same one that supersedes/deletes the document
version or changes an escalation rule — so there is no window in which a stale proposal can be
approved or executed. Approval and retry refuse stale proposals (review.py); the explicit way out is
Reprocess (workflow.reprocess), which re-runs the workflow against current documentation and rules
and adds a new proposal version.

Covered triggers:
- a document version the proposal's evidence references (cited *or* retrieved) is superseded or deleted;
- escalation rules change so that the set of rules matching the request (or a matching rule's effect)
  differs from what the proposal recorded.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from . import audit, rules
from .models import (Approval, Document, DocumentVersion, Proposal, ProposalEvidence, ProposalVersion,
                     Subscription, SupportRequest)
from .workflow import transition

PENDING_STATES = ("awaiting_review", "failed")


def _pending(db: Session, workspace_id: uuid.UUID, *extra):
    """Pending requests with their open proposal's current version, row-locked so approval/retry
    (which lock the same request row) serialize with invalidation."""
    return db.execute(
        select(SupportRequest, Proposal, ProposalVersion)
        .join(Proposal, Proposal.request_id == SupportRequest.id)
        .join(ProposalVersion, (ProposalVersion.proposal_id == Proposal.id)
              & (ProposalVersion.version == Proposal.current_version))
        .where(SupportRequest.workspace_id == workspace_id, SupportRequest.state.in_(PENDING_STATES),
               Proposal.status == "open", *extra)
        .with_for_update(of=SupportRequest)
    ).all()


def mark_stale(db: Session, req: SupportRequest, proposal: Proposal, pv: ProposalVersion, reason: str,
               actor: str) -> None:
    proposal.status, proposal.stale_reason = "stale", reason
    proposal.stale_at = datetime.now(timezone.utc)
    invalidated = db.query(Approval).filter(
        Approval.proposal_id == proposal.id, Approval.status == "active", Approval.decision == "approved"
    ).update({"status": "invalidated", "invalidated_reason": f"Evidence changed: {reason}"})
    transition(db, req, "stale", actor, reason)
    audit.record(db, workspace_id=req.workspace_id, actor=actor, event="proposal.stale", request_id=req.id,
                 demo_session_id=req.demo_session_id,
                 summary={"version": pv.version, "reason": reason, "approvals_invalidated": invalidated})


def invalidate_for_document_versions(db: Session, workspace_id: uuid.UUID, retired: dict[uuid.UUID, str],
                                     actor: str) -> list[uuid.UUID]:
    """`retired` maps document_version_id -> human description of what happened to it
    (e.g. "'Refund Policy' v1 was superseded by v2"). Returns the request ids marked stale."""
    if not retired:
        return []
    ids = list(retired)
    uses_retired = exists().where(ProposalEvidence.proposal_version_id == ProposalVersion.id,
                                  ProposalEvidence.document_version_id.in_(ids))
    out = []
    for req, proposal, pv in _pending(db, workspace_id, uses_retired):
        used = set(db.scalars(select(ProposalEvidence.document_version_id).where(
            ProposalEvidence.proposal_version_id == pv.id, ProposalEvidence.document_version_id.in_(ids))))
        reason = "Evidence changed: " + "; ".join(sorted(retired[v] for v in used)) + "."
        mark_stale(db, req, proposal, pv, reason, actor)
        out.append(req.id)
    return out


def describe_version(db: Session, version: DocumentVersion, outcome: str) -> str:
    doc = db.get(Document, version.document_id)
    return f"'{doc.title}' v{version.version} was {outcome}"


def invalidate_for_rule_change(db: Session, workspace_id: uuid.UUID, change: str, actor: str) -> list[uuid.UUID]:
    """Re-evaluate escalation rules for every pending proposal; stale those whose matching rules differ."""
    out = []
    for req, proposal, pv in _pending(db, workspace_id):
        content = pv.content
        plan = db.scalar(select(Subscription.plan).where(Subscription.workspace_id == workspace_id,
                                                         Subscription.customer_id == req.customer_id))
        now = {(h.key, h.effect) for _, h in rules.evaluate(
            db, workspace_id, category=content["category"], text=f"{req.subject}\n{req.body}", plan=plan)}
        before = {(h["key"], h["effect"]) for h in content.get("rule_hits", [])}
        if now == before:
            continue
        added = sorted(k for k, _ in now - before)
        removed = sorted(k for k, _ in before - now)
        parts = [f"now applies: {', '.join(added)}" if added else "",
                 f"no longer applies (or changed): {', '.join(removed)}" if removed else ""]
        reason = f"Escalation rules changed ({change}); " + "; ".join(p for p in parts if p) + "."
        mark_stale(db, req, proposal, pv, reason, actor)
        out.append(req.id)
    return out
