"""Who is calling, and what they may see. Derived only from server-side session records.

- Reviewer: signed in, member of the workspace, operates on workspace-scope rows
  (demo_session_id IS NULL).
- Visitor: anonymous demo session, operates only on rows tagged with their demo_session_id.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, DemoSession, Membership, Reviewer, Workspace
from .security import token_hash

REVIEWER_COOKIE = "ro_session"
DEMO_COOKIE = "ro_demo"
CUSTOMER_COOKIE = "ro_customer"


@dataclass(frozen=True)
class Actor:
    kind: Literal["reviewer", "visitor"]
    workspace_id: uuid.UUID
    workspace_slug: str
    reviewer_id: uuid.UUID | None
    demo_session_id: uuid.UUID | None
    label: str

    @property
    def is_reviewer(self) -> bool:
        return self.kind == "reviewer"


def scope_clause(actor: Actor, model):
    """Row filter for session-scoped tables (requests, tickets created by execution, ...)."""
    if actor.demo_session_id is not None:
        return model.demo_session_id == actor.demo_session_id
    return model.demo_session_id.is_(None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def current_reviewer(request: Request, db: Session) -> Reviewer | None:
    token = request.cookies.get(REVIEWER_COOKIE)
    if not token:
        return None
    sess = db.get(AuthSession, token_hash(token))
    if sess is None or sess.expires_at < _now():
        return None
    return db.get(Reviewer, sess.reviewer_id)


def current_demo_session(request: Request, db: Session) -> DemoSession | None:
    token = request.cookies.get(DEMO_COOKIE)
    if not token:
        return None
    ds = db.scalar(select(DemoSession).where(DemoSession.token_hash == token_hash(token)))
    if ds is None or ds.expires_at < _now():
        return None
    return ds


def get_workspace(ws: str, db: Session) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.slug == ws))
    if workspace is None:
        raise HTTPException(404, "Workspace not found")
    return workspace


def actor_for_workspace(ws: str, request: Request, db: Session = Depends(get_db)) -> Actor:
    workspace = get_workspace(ws, db)
    reviewer = current_reviewer(request, db)
    if reviewer is not None:
        member = db.scalar(select(Membership).where(
            Membership.reviewer_id == reviewer.id, Membership.workspace_id == workspace.id))
        if member is not None:
            return Actor("reviewer", workspace.id, workspace.slug, reviewer.id, None, f"reviewer:{reviewer.email}")
    demo = current_demo_session(request, db)
    if demo is not None and workspace.settings.get("demo_enabled", False):
        return Actor("visitor", workspace.id, workspace.slug, None, demo.id, f"visitor:{str(demo.id)[:8]}")
    raise HTTPException(401, "No session. Start a demo session or sign in.")


def require_reviewer(actor: Actor = Depends(actor_for_workspace)) -> Actor:
    if not actor.is_reviewer:
        raise HTTPException(403, "Reviewer sign-in required for this action.")
    return actor
