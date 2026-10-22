"""Auth, demo sessions, meta, tickets and customers."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..context import (CUSTOMER_COOKIE, DEMO_COOKIE, REVIEWER_COOKIE, Actor, actor_for_workspace,
                       current_demo_session, current_reviewer, require_reviewer)
from ..db import get_db
from ..models import (AiRun, AuditLog, AuthSession, Customer, CustomerSession, DemoSession, Document, DocumentVersion,
                      Execution, Membership,
                      Reviewer, Subscription, SupportRequest, Ticket, Workspace)
from ..schemas import CustomerSessionIn, LoginIn
from ..security import new_token, token_hash, verify_password
from .serializers import ticket_dict

router = APIRouter(prefix="/api")


def _now():
    return datetime.now(timezone.utc)


def _set_cookie(response: Response, name: str, value: str, hours: int) -> None:
    response.set_cookie(name, value, max_age=hours * 3600, httponly=True, samesite="lax",
                        secure=get_settings().cookie_secure, path="/")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/meta")
def meta(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    reviewer = current_reviewer(request, db)
    workspaces = db.scalars(select(Workspace).order_by(Workspace.name)).all()
    return {
        "mode": s.ai_mode,
        "provider_label": "Simulated AI — demo mode" if s.ai_mode == "demo" else "Claude (live)",
        "live_configured": bool(s.anthropic_api_key),  # never the key itself
        "reviewer": None if reviewer is None else {"email": reviewer.email, "name": reviewer.name},
        "workspaces": [{"slug": w.slug, "name": w.name, "profile": w.profile,
                        "demo_scenarios": w.settings.get("demo_scenarios", []),
                        "ticket_groups": w.settings.get("ticket_groups", [])} for w in workspaces],
    }


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    reviewer = db.scalar(select(Reviewer).where(Reviewer.email == body.email.strip().lower()))
    if reviewer is None or not verify_password(reviewer.password_hash, body.password):
        raise HTTPException(401, "Invalid email or password.")
    token = new_token()
    hours = get_settings().session_ttl_hours
    db.add(AuthSession(token_hash=token_hash(token), reviewer_id=reviewer.id, expires_at=_now() + timedelta(hours=hours)))
    db.commit()
    _set_cookie(response, REVIEWER_COOKIE, token, hours)
    return {"email": reviewer.email, "name": reviewer.name}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REVIEWER_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        db.commit()
    response.delete_cookie(REVIEWER_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, db: Session = Depends(get_db)):
    reviewer = current_reviewer(request, db)
    if reviewer is None:
        return {"reviewer": None}
    slugs = db.scalars(select(Workspace.slug).join(Membership, Membership.workspace_id == Workspace.id)
                       .where(Membership.reviewer_id == reviewer.id)).all()
    return {"reviewer": {"email": reviewer.email, "name": reviewer.name, "workspaces": slugs}}


@router.post("/demo/session")
def demo_session(request: Request, response: Response, db: Session = Depends(get_db)):
    ds = current_demo_session(request, db)
    if ds is None:
        token = new_token()
        hours = get_settings().demo_session_ttl_hours
        ds = DemoSession(token_hash=token_hash(token), expires_at=_now() + timedelta(hours=hours))
        db.add(ds)
        db.commit()
        _set_cookie(response, DEMO_COOKIE, token, hours)
    return {"demo_session": str(ds.id)[:8]}


@router.post("/demo/reset")
def demo_reset(request: Request, db: Session = Depends(get_db)):
    """Deletes only rows tagged with the caller's own demo session."""
    ds = current_demo_session(request, db)
    if ds is None:
        raise HTTPException(401, "No demo session.")
    counts = {}
    for model in (AiRun, AuditLog, Execution, Ticket, CustomerSession, SupportRequest):
        counts[model.__tablename__] = db.execute(delete(model).where(model.demo_session_id == ds.id)).rowcount
    db.commit()
    return {"reset": True, "deleted": counts}


@router.get("/w/{ws}/tickets")
def tickets(actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    q = select(Ticket).where(Ticket.workspace_id == actor.workspace_id)
    if actor.demo_session_id is not None:
        q = q.where((Ticket.demo_session_id.is_(None)) | (Ticket.demo_session_id == actor.demo_session_id))
    else:
        q = q.where(Ticket.demo_session_id.is_(None))
    return {"tickets": [ticket_dict(t) for t in db.scalars(q.order_by(Ticket.created_at.desc()))]}


@router.get("/w/{ws}/customers")
def customers(actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    rows = db.execute(select(Customer, Subscription.plan).join(Subscription, Subscription.customer_id == Customer.id)
                      .where(Customer.workspace_id == actor.workspace_id).order_by(Customer.company_name)).all()
    return {"customers": [{"id": str(c.id), "company_name": c.company_name, "account_ref": c.account_ref,
                           "contact_name": c.contact_name, "plan": plan, "is_synthetic": c.is_synthetic}
                          for c, plan in rows]}


@router.post("/w/{ws}/customer-session")
def customer_session(body: CustomerSessionIn, response: Response, actor: Actor = Depends(actor_for_workspace),
                     db: Session = Depends(get_db)):
    """Issue a server-validated synthetic customer identity for submitting requests."""
    c = db.scalar(select(Customer).where(Customer.id == body.customer_id, Customer.workspace_id == actor.workspace_id))
    if c is None or not c.is_synthetic:
        raise HTTPException(404, "Synthetic customer not found in this workspace.")
    token = new_token()
    db.add(CustomerSession(token_hash=token_hash(token), workspace_id=actor.workspace_id, customer_id=c.id,
                           demo_session_id=actor.demo_session_id, expires_at=_now() + timedelta(hours=2)))
    db.commit()
    _set_cookie(response, CUSTOMER_COOKIE, token, 2)
    return {"customer": {"id": str(c.id), "company_name": c.company_name, "contact_name": c.contact_name,
                         "is_synthetic": True}}


@router.get("/w/{ws}/admin/settings")
def admin_settings(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Reviewer-only. Workspace configuration (no credentials are stored in settings)."""
    w = db.get(Workspace, actor.workspace_id)
    return {"slug": w.slug, "name": w.name, "profile": w.profile, "settings": w.settings}


@router.get("/w/{ws}/admin/documents")
def admin_documents(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Reviewer-only. Knowledge-base documents and their versions / import status."""
    docs = db.scalars(select(Document).where(Document.workspace_id == actor.workspace_id).order_by(Document.title)).all()
    out = []
    for d in docs:
        versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)
                              .order_by(DocumentVersion.version.desc())).all()
        out.append({"id": str(d.id), "slug": d.slug, "title": d.title, "status": d.status,
                    "versions": [{"id": str(v.id), "version": v.version, "status": v.status,
                                  "format": v.source_format, "import_error": v.import_error,
                                  "created_at": v.created_at.isoformat()} for v in versions]})
    return {"documents": out}
