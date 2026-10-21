"""Typed tools used by the workflow (and, in live mode, offered to the model).

Rules enforced here, in ordinary code:
- Every tool receives a ToolContext built by the server. workspace_id and customer_id are
  never taken from model output or from the customer's message.
- Every query is scoped by ctx.workspace_id and, for account data, ctx.customer_id.
- Arguments and outputs are validated with Pydantic; only allowlisted tools can run.
- Every call is audited with timing, a concise result summary and any error.
- propose_ticket_action is pure validation: it cannot write tickets.
"""
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, retrieval
from .config import get_settings
from .models import AccountUser, Customer, Invoice, Subscription, Ticket, Workspace
from .schemas import (
    AccountUserFact,
    CustomerFacts,
    EmptyArgs,
    GetTicketsArgs,
    InvoiceFact,
    LookupCustomerArgs,
    Passage,
    ProposedTicketAction,
    SearchKnowledgeBaseArgs,
    SearchResults,
    SubscriptionFacts,
    TicketAction,
    TicketFact,
    TicketList,
)


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class ToolContext:
    db: Session
    workspace_id: uuid.UUID
    customer_id: uuid.UUID | None
    demo_session_id: uuid.UUID | None
    actor: str
    request_id: uuid.UUID | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(dt: datetime | None) -> int | None:
    return None if dt is None else max(0, (_now() - dt).days)


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _require_customer(ctx: ToolContext) -> Customer:
    if ctx.customer_id is None:
        raise ToolError("No authorized customer for this request.")
    customer = ctx.db.scalar(select(Customer).where(
        Customer.id == ctx.customer_id, Customer.workspace_id == ctx.workspace_id))
    if customer is None:
        raise ToolError("Authorized customer not found in this workspace.")
    return customer


# --- tools ----------------------------------------------------------------------

def lookup_customer(ctx: ToolContext, args: LookupCustomerArgs) -> CustomerFacts:
    """Returns the *authorized* customer only. Emails mentioned in the message that belong to
    anyone else are reported as ignored — they never select a different account."""
    customer = _require_customer(ctx)
    ws = ctx.db.get(Workspace, ctx.workspace_id)
    roles = ws.settings.get("roles", {})
    users = ctx.db.scalars(select(AccountUser).where(
        AccountUser.workspace_id == ctx.workspace_id, AccountUser.customer_id == customer.id,
        AccountUser.status == "active").order_by(AccountUser.name)).all()
    own_emails = {customer.contact_email.lower(), *(u.email.lower() for u in users)}
    foreign = sorted({e.lower() for e in args.mentioned_emails} - own_emails)
    facts = [AccountUserFact(name=u.name, email=u.email, role=u.role,
                             has_reporting="reporting" in roles.get(u.role, [])) for u in users]
    meta = dict(customer.meta or {})
    connectors = meta.pop("connectors", [])
    return CustomerFacts(
        customer_id=customer.id, account_ref=customer.account_ref, company_name=customer.company_name,
        contact_name=customer.contact_name, contact_email=customer.contact_email,
        is_synthetic=customer.is_synthetic, users=facts,
        admins=[u.name for u in facts if u.role == "Admin"],
        users_without_reporting=[u.name for u in facts if not u.has_reporting],
        connectors=connectors, other_metadata=meta, foreign_emails_ignored=foreign,
    )


def get_subscription(ctx: ToolContext, args: EmptyArgs) -> SubscriptionFacts:
    customer = _require_customer(ctx)
    sub = ctx.db.scalar(select(Subscription).where(
        Subscription.workspace_id == ctx.workspace_id, Subscription.customer_id == customer.id))
    if sub is None:
        raise ToolError("No subscription on file for this customer.")
    invoices = ctx.db.scalars(select(Invoice).where(
        Invoice.workspace_id == ctx.workspace_id, Invoice.customer_id == customer.id,
        Invoice.issued_at >= sub.current_period_start).order_by(Invoice.issued_at)).all()
    return SubscriptionFacts(
        plan=sub.plan, status=sub.status, billing_cycle=sub.billing_cycle,
        seats_purchased=sub.seats_purchased, seats_used=sub.seats_used,
        seats_available=max(0, sub.seats_purchased - sub.seats_used),
        price_per_seat=_money(sub.price_per_seat_cents), features=list(sub.features),
        previous_plan=sub.previous_plan, plan_changed_at=sub.plan_changed_at,
        plan_changed_days_ago=_days_ago(sub.plan_changed_at),
        current_period_start=sub.current_period_start, current_period_end=sub.current_period_end,
        invoices_this_period=[InvoiceFact(
            number=i.number, kind=i.kind, description=i.description, amount=_money(i.amount_cents),
            status=i.status, issued_at=i.issued_at, days_ago=_days_ago(i.issued_at) or 0) for i in invoices],
    )


def search_knowledge_base(ctx: ToolContext, args: SearchKnowledgeBaseArgs) -> SearchResults:
    hits = retrieval.search(ctx.db, ctx.workspace_id, args.query, args.top_k)
    return SearchResults(passages=[Passage(**h.__dict__) for h in hits])


def get_existing_tickets(ctx: ToolContext, args: GetTicketsArgs) -> TicketList:
    customer = _require_customer(ctx)
    q = select(Ticket).where(Ticket.workspace_id == ctx.workspace_id, Ticket.customer_id == customer.id)
    # Visitors see shared seed tickets plus their own sandbox tickets; reviewers see workspace tickets.
    if ctx.demo_session_id is not None:
        q = q.where((Ticket.demo_session_id.is_(None)) | (Ticket.demo_session_id == ctx.demo_session_id))
    else:
        q = q.where(Ticket.demo_session_id.is_(None))
    if not args.include_closed:
        q = q.where(Ticket.status != "solved")
    rows = ctx.db.scalars(q.order_by(Ticket.created_at.desc()).limit(args.limit)).all()
    return TicketList(tickets=[TicketFact(
        id=t.id, number=t.number, subject=t.subject, category=t.category, priority=t.priority,
        status=t.status, group=t.group, created_days_ago=_days_ago(t.created_at) or 0) for t in rows])


def propose_ticket_action(ctx: ToolContext, args: TicketAction) -> ProposedTicketAction:
    """Validate a proposed ticket action. Never writes anything."""
    problems: list[str] = []
    ws = ctx.db.get(Workspace, ctx.workspace_id)
    if args.type == "create_ticket":
        for field in ("subject", "body", "priority", "group", "status"):
            if not getattr(args, field):
                problems.append(f"create_ticket requires '{field}'.")
        if args.group and args.group not in ws.settings.get("ticket_groups", []):
            problems.append(f"Group '{args.group}' is not an allowed destination.")
        if args.ticket_id is not None:
            problems.append("create_ticket must not reference an existing ticket.")
    elif args.type == "add_note":
        if args.ticket_id is None or not args.body:
            problems.append("add_note requires 'ticket_id' and 'body'.")
        else:
            customer = _require_customer(ctx)
            t = ctx.db.scalar(select(Ticket).where(
                Ticket.id == args.ticket_id, Ticket.workspace_id == ctx.workspace_id,
                Ticket.customer_id == customer.id))
            if t is None:
                problems.append("Ticket not found for this customer.")
    return ProposedTicketAction(action=args, valid=not problems, problems=problems)


# --- registry -------------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    fn: Callable
    args_model: type[BaseModel]
    out_model: type[BaseModel]
    description: str


TOOLS: dict[str, ToolSpec] = {
    "lookup_customer": ToolSpec(lookup_customer, LookupCustomerArgs, CustomerFacts,
                                "Account profile and users for the authorized customer."),
    "get_subscription": ToolSpec(get_subscription, EmptyArgs, SubscriptionFacts,
                                 "Plan, seats, features and invoices for the authorized customer."),
    "search_knowledge_base": ToolSpec(search_knowledge_base, SearchKnowledgeBaseArgs, SearchResults,
                                      "Semantic search over the workspace's active documentation."),
    "get_existing_tickets": ToolSpec(get_existing_tickets, GetTicketsArgs, TicketList,
                                     "Recent tickets for the authorized customer."),
    "propose_ticket_action": ToolSpec(propose_ticket_action, TicketAction, ProposedTicketAction,
                                      "Validate a proposed ticket change (does not execute it)."),
}


def _summarize(name: str, out: BaseModel) -> dict:
    if isinstance(out, CustomerFacts):
        s = {"customer": out.company_name, "users": len(out.users),
             "without_reporting": len(out.users_without_reporting)}
        if out.foreign_emails_ignored:
            s["foreign_emails_ignored"] = out.foreign_emails_ignored
        return s
    if isinstance(out, SubscriptionFacts):
        return {"plan": out.plan, "status": out.status, "previous_plan": out.previous_plan,
                "seats": f"{out.seats_used}/{out.seats_purchased}", "invoices_this_period": len(out.invoices_this_period)}
    if isinstance(out, SearchResults):
        return {"passages": [{"chunk_id": str(p.chunk_id), "doc": p.doc_slug, "version": p.version,
                              "section": p.section, "score": p.score} for p in out.passages]}
    if isinstance(out, TicketList):
        return {"tickets": [f"{t.number} ({t.status})" for t in out.tickets]}
    if isinstance(out, ProposedTicketAction):
        return {"type": out.action.type, "valid": out.valid, "problems": out.problems}
    return {}


def call_tool(ctx: ToolContext, name: str, raw_args: dict):
    """The only way the workflow runs a tool: allowlist → validate args → run → validate output → audit."""
    spec = TOOLS.get(name)
    if spec is None:
        audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="tool.rejected",
                     request_id=ctx.request_id, demo_session_id=ctx.demo_session_id, tool_name=name,
                     error="Tool is not allowlisted.")
        raise ToolError(f"Tool '{name}' is not allowlisted.")
    started = time.perf_counter()
    try:
        args = spec.args_model.model_validate(raw_args)
        out = spec.out_model.model_validate(spec.fn(ctx, args))
    except (ToolError, ValidationError) as exc:
        audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="tool.error",
                     request_id=ctx.request_id, demo_session_id=ctx.demo_session_id, tool_name=name,
                     summary={"args": raw_args}, duration_ms=int((time.perf_counter() - started) * 1000),
                     error=str(exc))
        raise ToolError(str(exc)) from exc
    audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="tool.call",
                 request_id=ctx.request_id, demo_session_id=ctx.demo_session_id, tool_name=name,
                 summary={"args": args.model_dump(mode="json"), "result": _summarize(name, out)},
                 duration_ms=int((time.perf_counter() - started) * 1000))
    return out


def default_top_k() -> int:
    return get_settings().retrieval_top_k
