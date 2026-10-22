"""Ticket adapter interface. Executions call adapters only after an approval exists."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..schemas import TicketAction


class AdapterError(Exception):
    pass


@dataclass
class TicketResult:
    ticket_id: uuid.UUID
    number: str
    created: bool  # False when the idempotency key matched an existing ticket/note
    external_id: str | None = None
    external_url: str | None = None


@dataclass(frozen=True)
class ExecutionTarget:
    workspace_id: uuid.UUID
    demo_session_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    request_id: uuid.UUID
    category: str


class TicketAdapter(ABC):
    name: str

    @abstractmethod
    def create_ticket(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult: ...

    @abstractmethod
    def add_note(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult: ...
