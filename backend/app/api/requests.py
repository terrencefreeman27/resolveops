"""Request, proposal and review endpoints. Every lookup is scoped by workspace and caller scope."""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import limits, review
from ..context import CUSTOMER_COOKIE, Actor, actor_for_workspace
from ..db import get_db
from ..providers import live_for
from ..models import Chunk, Customer, CustomerSession, Document, DocumentVersion, SupportRequest
from ..schemas import ApproveIn, EditProposalIn, RejectIn, SubmitRequestIn
from ..security import token_hash
from ..workflow import reprocess, run_request
from .serializers import citation_status, request_detail, request_summary, visible_requests_clause

router = APIRouter(prefix="/api/w/{ws}")


def _get_visible(db: Session, actor: Actor, request_id: uuid.UUID) -> SupportRequest:
    r = db.scalar(select(SupportRequest).where(SupportRequest.id == request_id, visible_requests_clause(actor)))
    if r is None:
        raise HTTPException(404, "Request not found.")
    return r


def _get_owned(db: Session, actor: Actor, request_id: uuid.UUID) -> SupportRequest:
    r = _get_visible(db, actor, request_id)
    if r.is_template:
        raise HTTPException(409, "Seeded inbox items are read-only; run the workflow to get your own copy.")
    return r


def _clone(db: Session, actor: Actor, t: SupportRequest) -> SupportRequest:
    r = SupportRequest(
        workspace_id=t.workspace_id, demo_session_id=actor.demo_session_id, customer_id=t.customer_id,
        submitted_via=t.submitted_via, from_name=t.from_name, from_email=t.from_email, subject=t.subject,
        body=t.body, scenario_key=t.scenario_key, is_template=False, source_request_id=t.id, state="received")
    db.add(r)
    db.flush()
    return r


@contextmanager
def _ai_gate(db: Session, actor: Actor, subject: str, body: str):
    """Decide live vs simulated for this caller and, for live, enforce input size, rate limits and
    budget *before* any row is written, then hold a concurrency slot for the run."""
    live = live_for(actor.is_reviewer)
    if not live:
        yield False
        return
    limits.check_input(subject, body)
    limits.preflight(db, actor.label)
    with limits.live_slot():
        yield True


@router.get("/requests")
def list_requests(state: str | None = None, category: str | None = None,
                  actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    q = select(SupportRequest).where(visible_requests_clause(actor))
    if state:
        q = q.where(SupportRequest.state == state)
    if category:
        q = q.where(SupportRequest.category == category)
    rows = db.scalars(q.order_by(SupportRequest.is_template, SupportRequest.received_at.desc())).all()
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.workspace_id == actor.workspace_id))}
    return {"requests": [request_summary(r, customers.get(r.customer_id)) for r in rows]}


@router.get("/requests/{request_id}")
def get_request(request_id: uuid.UUID, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    return request_detail(db, actor, _get_visible(db, actor, request_id))


@router.post("/scenarios/{key}/run")
def run_scenario(key: str, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    t = db.scalar(select(SupportRequest).where(SupportRequest.workspace_id == actor.workspace_id,
                                               SupportRequest.is_template.is_(True), SupportRequest.scenario_key == key))
    if t is None:
        raise HTTPException(404, "Unknown demo scenario.")
    with _ai_gate(db, actor, t.subject, t.body) as live:
        r = _clone(db, actor, t)
        run_request(db, r, actor.label, live=live)
    return request_detail(db, actor, r)


@router.post("/requests/{request_id}/run")
def run(request_id: uuid.UUID, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    r = _get_visible(db, actor, request_id)
    with _ai_gate(db, actor, r.subject, r.body) as live:
        if r.is_template:
            r = _clone(db, actor, r)
            run_request(db, r, actor.label, live=live)
        elif r.state == "received":
            run_request(db, r, actor.label, live=live)
        else:
            reprocess(db, r, actor.label, live=live)
    return request_detail(db, actor, r)


@router.post("/requests")
def submit(body: SubmitRequestIn, request: Request, actor: Actor = Depends(actor_for_workspace),
           db: Session = Depends(get_db)):
    """Customer identity comes from a server-issued synthetic customer session (or, for a signed-in
    reviewer, an explicitly selected customer in this workspace) — never from the message text."""
    customer = None
    if body.customer_id is not None:
        if not actor.is_reviewer:
            raise HTTPException(403, "Visitors submit as a synthetic customer session, not by customer id.")
        customer = db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                    Customer.workspace_id == actor.workspace_id))
        via = "reviewer"
    else:
        token = request.cookies.get(CUSTOMER_COOKIE)
        cs = db.get(CustomerSession, token_hash(token)) if token else None
        if (cs and cs.workspace_id == actor.workspace_id and cs.demo_session_id == actor.demo_session_id
                and cs.expires_at > datetime.now(timezone.utc)):
            customer = db.get(Customer, cs.customer_id)
        via = "customer_session"
    if customer is None:
        raise HTTPException(403, "No authorized customer for this submission.")
    with _ai_gate(db, actor, body.subject, body.body) as live:
        r = SupportRequest(workspace_id=actor.workspace_id, demo_session_id=actor.demo_session_id,
                           customer_id=customer.id, submitted_via=via, from_name=customer.contact_name,
                           from_email=customer.contact_email, subject=body.subject, body=body.body, state="received")
        db.add(r)
        db.flush()
        run_request(db, r, actor.label, live=live)
    return request_detail(db, actor, r)


@router.put("/requests/{request_id}/proposal")
def edit(request_id: uuid.UUID, body: EditProposalIn, actor: Actor = Depends(actor_for_workspace),
         db: Session = Depends(get_db)):
    r = _get_owned(db, actor, request_id)
    review.edit(db, r.id, actor.label, body)
    return request_detail(db, actor, r)


@router.post("/requests/{request_id}/approve")
def approve(request_id: uuid.UUID, body: ApproveIn, actor: Actor = Depends(actor_for_workspace),
            db: Session = Depends(get_db)):
    # Visitors may approve only inside their own sandbox (_get_owned enforces scope); workspace-scope
    # requests are only visible to signed-in reviewers.
    r = _get_owned(db, actor, request_id)
    review.approve(db, r.id, actor.label, body)
    return request_detail(db, actor, r)


@router.post("/requests/{request_id}/reject")
def reject(request_id: uuid.UUID, body: RejectIn, actor: Actor = Depends(actor_for_workspace),
           db: Session = Depends(get_db)):
    r = _get_owned(db, actor, request_id)
    review.reject(db, r.id, actor.label, body)
    return request_detail(db, actor, r)


@router.post("/requests/{request_id}/retry")
def retry(request_id: uuid.UUID, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    r = _get_owned(db, actor, request_id)
    review.retry(db, r.id, actor.label)
    return request_detail(db, actor, r)


@router.post("/requests/{request_id}/escalate-internal")
def escalate_internal(request_id: uuid.UUID, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    # Explicit reviewer action after a failed GitHub execution; never automatic.
    r = _get_owned(db, actor, request_id)
    review.escalate_internal(db, r.id, actor.label)
    return request_detail(db, actor, r)


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: uuid.UUID, actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    row = db.execute(
        select(Chunk, Document, DocumentVersion)
        .join(Document, Document.id == Chunk.document_id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(Chunk.id == chunk_id, Chunk.workspace_id == actor.workspace_id)).first()
    if row is None:
        raise HTTPException(404, "Passage not found.")
    c, d, v = row
    # A citation always opens the exact version it cites, even after that version is superseded.
    return {"chunk_id": str(c.id), "document_id": str(d.id), "doc_slug": d.slug, "doc_title": d.title,
            "version": v.version, "version_status": v.status, "section": c.section, "text": c.text,
            "active": c.active, "document_content": v.content, "document_status": d.status,
            "current_version": citation_status(db, [v.id]).get(v.id, {}).get("current_version")}
