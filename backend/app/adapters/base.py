"""Ticket adapter interface. Executions call adapters only after an approval exists."""
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..schemas import TicketAction


class AdapterError(Exception):
    """retryable=False tells the executor not to repeat the attempt (the adapter already retried
    internally, or the failure is permanent, e.g. bad credentials). The reviewer can still retry."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class TicketResult:
    ticket_id: uuid.UUID
    number: str
    created: bool  # False when the idempotency key matched an existing ticket/note
    external_id: str | None = None
    external_url: str | None = None
    external_number: int | None = None


@dataclass(frozen=True)
class ExecutionTarget:
    workspace_id: uuid.UUID
    demo_session_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    request_id: uuid.UUID
    category: str
    next_action: str = ""
    not_before: datetime | None = None  # when the execution was created (bounds external lookups)


class TicketAdapter(ABC):
    name: str

    @abstractmethod
    def create_ticket(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult: ...

    @abstractmethod
    def add_note(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult: ...
