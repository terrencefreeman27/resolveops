"""Append-only audit log writer."""
import uuid

from sqlalchemy.orm import Session

from .models import AuditLog


def record(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor: str,
    event: str,
    request_id: uuid.UUID | None = None,
    demo_session_id: uuid.UUID | None = None,
    tool_name: str | None = None,
    summary: dict | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    db.add(AuditLog(
        workspace_id=workspace_id, actor=actor, event=event, request_id=request_id,
        demo_session_id=demo_session_id, tool_name=tool_name, summary=summary or {},
        duration_ms=duration_ms, error=error[:2000] if error else None,
    ))
