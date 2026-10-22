"""Code-side gate for tool calls requested by the live model.

The model only *asks* for a tool. This gate decides, in ordinary code, whether the call runs:
- the tool must be on the allowlist (tools.TOOLS); anything else is refused and audited;
- arguments may not carry authority (workspace/customer/account ids, approval flags) — the
  server-built ToolContext is the only source of who/where; such calls are refused and audited;
- an email or ticket id that belongs to another customer is refused (ticket) or flagged and
  never looked up (email), and audited as a cross-customer attempt;
- arguments and outputs are validated by tools.call_tool, which also audits every call.

Refusals are returned to the model as error tool results so it can continue the normal task;
they are also surfaced to the reviewer as risk flags on the proposal.
"""
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy import select

from .. import audit
from ..models import Ticket
from ..schemas import CustomerFacts, Passage, SearchResults, SubscriptionFacts, TicketFact, TicketList
from ..tools import TOOLS, ToolContext, ToolError, call_tool
from .live_prompt import render_tool_output

# Argument names that would claim identity or authority. The model never supplies these.
AUTHORITY_KEYS = {
    "workspace_id", "workspace", "customer_id", "customer", "account_id", "account_ref", "account",
    "demo_session_id", "reviewer_id", "actor", "approved", "approval", "approve", "role", "is_admin",
    "customer_email", "email",
}


@dataclass
class ToolOutcome:
    content: str
    is_error: bool


@dataclass
class ToolGate:
    ctx: ToolContext
    customer: CustomerFacts | None = None
    subscription: SubscriptionFacts | None = None
    tickets: list[TicketFact] | None = None
    passages: list[Passage] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    mentioned_emails: list[str] = field(default_factory=list)
    security_flags: list[str] = field(default_factory=list)
    calls: int = 0

    def _refuse(self, name: str, raw: object, reason: str, message: str, event: str = "tool.refused") -> ToolOutcome:
        audit.record(self.ctx.db, workspace_id=self.ctx.workspace_id, actor=self.ctx.actor, event=event,
                     request_id=self.ctx.request_id, demo_session_id=self.ctx.demo_session_id,
                     tool_name=name[:48], summary={"reason": reason, "args": raw if isinstance(raw, dict) else str(raw)[:200]},
                     error=message)
        flag = f"Blocked: {message}"
        if flag not in self.security_flags:
            self.security_flags.append(flag)
        return ToolOutcome(f"Refused: {message}", True)

    def run(self, name: str, raw: object) -> ToolOutcome:
        self.calls += 1
        if name not in TOOLS:
            return self._refuse(name, raw, "not_allowlisted", f"the model requested tool '{name[:48]}', which is not allowlisted.")
        if not isinstance(raw, dict):
            return self._refuse(name, raw, "invalid_arguments", f"arguments for '{name}' were not an object.")
        claimed = sorted(AUTHORITY_KEYS & {k.lower() for k in raw})
        if claimed:
            return self._refuse(name, raw, "authority_argument",
                                f"the model tried to pass {', '.join(claimed)} to '{name}'; identity comes from the server session only.",
                                event="access.cross_customer_refused")
        if name == "propose_ticket_action" and raw.get("ticket_id"):
            if not self._ticket_is_authorized(raw["ticket_id"]):
                return self._refuse(name, raw, "foreign_ticket",
                                    "the model referenced a ticket that does not belong to the authorized customer.",
                                    event="access.cross_customer_refused")
        try:
            out = call_tool(self.ctx, name, raw)
        except ToolError as exc:
            return ToolOutcome(f"Error: {exc}", True)
        self._collect(name, raw, out)
        return ToolOutcome(render_tool_output(name, out), False)

    def _ticket_is_authorized(self, ticket_id: object) -> bool:
        try:
            tid = uuid.UUID(str(ticket_id))
        except ValueError:
            return True  # malformed ids are rejected by argument validation in call_tool
        if self.ctx.customer_id is None:
            return False
        return self.ctx.db.scalar(select(Ticket.id).where(
            Ticket.id == tid, Ticket.workspace_id == self.ctx.workspace_id,
            Ticket.customer_id == self.ctx.customer_id)) is not None

    def _collect(self, name: str, raw: dict, out: BaseModel) -> None:
        if isinstance(out, CustomerFacts):
            self.customer = out
            for e in raw.get("mentioned_emails", []):
                if e.lower() not in self.mentioned_emails:
                    self.mentioned_emails.append(e.lower())
            if out.foreign_emails_ignored:
                audit.record(self.ctx.db, workspace_id=self.ctx.workspace_id, actor=self.ctx.actor,
                             event="access.cross_customer_refused", request_id=self.ctx.request_id,
                             demo_session_id=self.ctx.demo_session_id, tool_name=name,
                             summary={"reason": "foreign_email", "emails": out.foreign_emails_ignored},
                             error="Emails that belong to other accounts were not looked up.")
                flag = "Blocked: other accounts mentioned (" + ", ".join(out.foreign_emails_ignored) + ") were not accessed."
                if flag not in self.security_flags:
                    self.security_flags.append(flag)
        elif isinstance(out, SubscriptionFacts):
            self.subscription = out
        elif isinstance(out, TicketList):
            self.tickets = out.tickets
        elif isinstance(out, SearchResults):
            self.queries.append(raw.get("query", ""))
            seen = {p.chunk_id for p in self.passages}
            self.passages.extend(p for p in out.passages if p.chunk_id not in seen)
