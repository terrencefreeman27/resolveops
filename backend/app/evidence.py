"""Insufficient / conflicting evidence check (SPEC §6: "If documentation is insufficient or
conflicting, ask for clarification or escalate").

Both checks are ordinary, explainable code — no model judgement:

- **Insufficient:** no passage retrieved for the request scores at or above the relevance threshold
  (cosine similarity; `RETRIEVAL_MIN_SCORE`, overridable per workspace as settings.retrieval_min_score).
- **Conflicting:** two relevant passages from current documents declare *different values for the same
  policy key*. Documents declare policy facts with a marker inside the section that states them, e.g.
  `<!-- policy plan_change.downgrade_effective: end_of_term -->` (parsed at import, documents.py).
  Because markers live on sections, a conflict only counts when both disagreeing sections were actually
  retrieved for this request.

If either check fails and the draft would *resolve*, the server changes it to an escalation to the
workspace's evidence-review group with a neutral holding reply. Clarify/escalate drafts are kept. The
check and its effect are stored on the proposal and shown to the reviewer; a reviewer edit cannot turn
such a proposal back into a confident resolve (review.edit).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Chunk, Workspace
from .schemas import ConflictValue, EvidenceCheck, PolicyConflict, ProposalContent, TicketAction


def threshold_for(ws: Workspace) -> float:
    v = (ws.settings or {}).get("retrieval_min_score")
    return float(v) if v is not None else get_settings().retrieval_min_score


def assess(db: Session, workspace_id: uuid.UUID, passages) -> EvidenceCheck:
    ws = db.get(Workspace, workspace_id)
    threshold = threshold_for(ws)
    best = max((p.score for p in passages), default=None)
    relevant = [p for p in passages if p.score >= threshold]
    if not relevant:
        return EvidenceCheck(status="insufficient", threshold=threshold, best_score=best, relevant_passages=0)
    facts = dict(db.execute(select(Chunk.id, Chunk.policy_facts).where(
        Chunk.workspace_id == workspace_id, Chunk.id.in_([p.chunk_id for p in relevant]))).all())
    by_key: dict[str, list[ConflictValue]] = {}
    for p in relevant:
        for key, value in (facts.get(p.chunk_id) or {}).items():
            by_key.setdefault(key, []).append(ConflictValue(
                value=value, document_id=p.document_id, doc_title=p.doc_title, version=p.version,
                section=p.section, chunk_id=p.chunk_id))
    conflicts = [PolicyConflict(key=k, values=v) for k, v in sorted(by_key.items())
                 if len({x.value.strip().lower() for x in v}) > 1]
    return EvidenceCheck(status="conflicting" if conflicts else "sufficient", threshold=threshold,
                         best_score=best, relevant_passages=len(relevant), conflicts=conflicts)


def _reason(check: EvidenceCheck) -> str:
    if check.status == "insufficient":
        best = f"{check.best_score:.2f}" if check.best_score is not None else "none"
        return (f"No documentation passage reached the relevance threshold ({check.threshold:.2f}; best match "
                f"{best}). The answer is not documented, so a person must answer it.")
    parts = []
    for c in check.conflicts:
        vals = "; ".join(f"'{v.doc_title}' v{v.version} says {v.value}" for v in c.values)
        parts.append(f"{c.key}: {vals}")
    return "Current documents disagree on the deciding policy — " + " | ".join(parts) + ". A person must confirm which is correct."


def apply(content: ProposalContent, check: EvidenceCheck, ws: Workspace, contact_name: str | None) -> ProposalContent:
    content.evidence_check = check
    if check.status == "sufficient":
        return content
    reason = _reason(check)
    if content.next_action != "resolve":
        content.escalation_reason = content.escalation_reason or reason
        return content
    group = (ws.settings or {}).get("evidence_review_group") or ((ws.settings or {}).get("ticket_groups") or [None])[0]
    signature = (ws.profile or {}).get("support_signature") or f"{ws.name} Support"
    first = (contact_name or "there").split()[0]
    content.next_action = "escalate"
    content.escalation_reason = reason
    content.draft_reply = (f"Hi {first},\n\nThanks for your question. We want to give you an accurate answer, so "
                           "a specialist on our team is confirming the details and will follow up with you shortly."
                           f"\n\nBest regards,\n{signature}")
    content.ticket_action = TicketAction(
        type="create_ticket", subject=f"Evidence review: {content.summary[:170]}",
        body=f"{content.summary}\n\n{reason}", priority="normal", group=group, status="open")
    check.effect = (f"Changed the drafted 'resolve' to 'escalate' ({check.status} evidence) and replaced the reply "
                    "with a holding message.")
    return content
