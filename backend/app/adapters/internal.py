"""Internal ticket system: rows in the `tickets` table, deduplicated by idempotency key."""
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Ticket, Workspace
from ..schemas import TicketAction
from .base import AdapterError, ExecutionTarget, TicketAdapter, TicketResult

# Test hook: number of upcoming calls that should fail (simulates an outage). Never set from input.
FAULTS = {"fail_next": 0, "fail_after_write": 0}


def _maybe_fail(key: str) -> None:
    if FAULTS[key] > 0:
        FAULTS[key] -= 1
        raise AdapterError(f"Simulated internal ticket system failure ({key}).")


class InternalTicketAdapter(TicketAdapter):
    name = "internal"

    def create_ticket(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult:
        existing = db.scalar(select(Ticket).where(Ticket.idempotency_key == idempotency_key))
        if existing is not None:
            return TicketResult(existing.id, existing.number, created=False)
        _maybe_fail("fail_next")
        ws = db.get(Workspace, target.workspace_id)
        seq = db.scalar(text("SELECT nextval('ticket_number_seq')"))
        t = Ticket(
            workspace_id=target.workspace_id, demo_session_id=target.demo_session_id,
            customer_id=target.customer_id, request_id=target.request_id,
            number=f"{ws.settings.get('ticket_prefix', 'T')}-{seq}", subject=action.subject, body=action.body,
            category=target.category, priority=action.priority, status=action.status, group=action.group,
            source="execution", adapter=self.name, idempotency_key=idempotency_key,
        )
        db.add(t)
        db.flush()  # the UNIQUE(idempotency_key) constraint is the last line of defence
        _maybe_fail("fail_after_write")
        return TicketResult(t.id, t.number, created=True)

    def add_note(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult:
        _maybe_fail("fail_next")
        t = db.scalar(select(Ticket).where(
            Ticket.id == action.ticket_id, Ticket.workspace_id == target.workspace_id,
            Ticket.customer_id == target.customer_id).with_for_update())
        if t is None or (t.demo_session_id is not None and t.demo_session_id != target.demo_session_id):
            raise AdapterError("Ticket not found for this customer.")
        note = {"body": action.body, "idempotency_key": idempotency_key, "at": datetime.now(timezone.utc).isoformat()}
        if target.demo_session_id is not None and t.demo_session_id is None:
            # Visitors never modify shared seed tickets: the note goes on a sandbox copy of the ticket.
            copy = db.scalar(select(Ticket).where(Ticket.idempotency_key == idempotency_key))
            if copy is not None:
                return TicketResult(copy.id, copy.number, created=False)
            copy = Ticket(workspace_id=t.workspace_id, demo_session_id=target.demo_session_id, customer_id=t.customer_id,
                          request_id=target.request_id, number=t.number, subject=t.subject, body=t.body,
                          category=t.category, priority=t.priority, status=t.status, group=t.group,
                          source="execution", adapter=self.name, idempotency_key=idempotency_key,
                          notes=[*t.notes, {**note, "sandbox_copy_of": str(t.id)}])
            db.add(copy)
            db.flush()
            return TicketResult(copy.id, copy.number, created=True)
        if any(n.get("idempotency_key") == idempotency_key for n in t.notes):
            return TicketResult(t.id, t.number, created=False)
        t.notes = [*t.notes, note]
        db.flush()
        return TicketResult(t.id, t.number, created=True)

def get_adapter(name: str) -> TicketAdapter:
    if name == "internal":
        return InternalTicketAdapter()
    raise AdapterError(f"Ticket adapter '{name}' is not available.")
