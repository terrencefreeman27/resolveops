"""The request workflow: one explicit state machine and the pipeline that drives it.

received → classified → context_resolved → retrieved → awaiting_review
awaiting_review → approved → executing → completed | failed      (see review.py)
Side exits: unsupported, error, rejected, stale. Reprocess returns to received.
"""
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import audit, rules
from .config import get_settings
from .models import AiRun, Proposal, ProposalEvidence, ProposalVersion, SupportRequest
from .providers import ProviderError, SynthesisInput, UnsupportedInDemo, Usage, get_provider
from .schemas import (
    AccountFact,
    Citation,
    Classification,
    ProposalContent,
    TicketAction,
    TicketList,
    action_hash,
)
from .tools import ToolContext, ToolError, call_tool, default_top_k

TRANSITIONS: dict[str, set[str]] = {
    "received": {"classified", "unsupported", "error"},
    "classified": {"context_resolved", "unsupported", "error"},
    "context_resolved": {"retrieved", "error"},
    "retrieved": {"awaiting_review", "error"},
    "awaiting_review": {"awaiting_review", "approved", "rejected", "stale"},
    "approved": {"executing"},
    "executing": {"completed", "failed"},
    "failed": {"executing", "awaiting_review"},  # retry, or edit → new version needs new approval
    "rejected": {"received"},
    "stale": {"received"},
    "error": {"received"},
    "unsupported": {"received"},
    "completed": set(),
}
TERMINAL = {"completed"}
RESOLUTION = {"resolve": "resolved", "clarify": "awaiting_customer", "escalate": "escalated"}


class InvalidTransition(Exception):
    pass


def transition(db: Session, req: SupportRequest, new_state: str, actor: str, reason: str | None = None) -> None:
    if new_state not in TRANSITIONS.get(req.state, set()):
        raise InvalidTransition(f"Cannot move request from '{req.state}' to '{new_state}'.")
    old = req.state
    req.state, req.state_reason = new_state, reason
    audit.record(db, workspace_id=req.workspace_id, actor=actor, event="state.changed", request_id=req.id,
                 demo_session_id=req.demo_session_id, summary={"from": old, "to": new_state, "reason": reason})


def tool_context(db: Session, req: SupportRequest, actor: str) -> ToolContext:
    """Trusted context for tools: workspace + authorized customer come from the request row,
    which the server populated from a validated session — never from model output."""
    return ToolContext(db=db, workspace_id=req.workspace_id, customer_id=req.customer_id,
                       demo_session_id=req.demo_session_id, actor=actor, request_id=req.id)


def _timed_ai(db: Session, req: SupportRequest, provider, step: str, fn):
    started = time.perf_counter()
    try:
        out = fn()
    except Exception as exc:
        audit.record(db, workspace_id=req.workspace_id, actor=f"ai:{provider.name}", event=f"ai.{step}",
                     request_id=req.id, demo_session_id=req.demo_session_id,
                     duration_ms=int((time.perf_counter() - started) * 1000), error=str(exc),
                     summary={"provider": provider.label})
        raise
    summary = {"provider": provider.label}
    if step == "classify":
        summary |= {"category": out.category, "priority": out.priority, "risk_flags": len(out.risk_flags)}
    else:
        summary |= {"next_action": out.next_action, "ticket_action": out.ticket_action.type,
                    "citations": len(out.citations)}
    audit.record(db, workspace_id=req.workspace_id, actor=f"ai:{provider.name}", event=f"ai.{step}",
                 request_id=req.id, demo_session_id=req.demo_session_id, summary=summary,
                 duration_ms=int((time.perf_counter() - started) * 1000))
    return out


def account_facts(customer, sub, tickets) -> list[AccountFact]:
    """Built by the server from tool results — the model never authors account facts."""
    f = [
        AccountFact(label="Account", value=f"{customer.company_name} ({customer.account_ref})"
                    + (" — synthetic" if customer.is_synthetic else ""), source="lookup_customer"),
        AccountFact(label="Plan", value=f"{sub.plan} · {sub.status} · {sub.billing_cycle}", source="get_subscription"),
    ]
    if sub.previous_plan and sub.plan_changed_days_ago is not None:
        f.append(AccountFact(label="Plan change", value=f"{sub.previous_plan} → {sub.plan}, "
                             f"{sub.plan_changed_days_ago} day(s) ago", source="get_subscription"))
    f.append(AccountFact(label="Seats", value=f"{sub.seats_used} used of {sub.seats_purchased}",
                         source="get_subscription"))
    f.append(AccountFact(label="Plan features", value=", ".join(sub.features), source="get_subscription"))
    f.append(AccountFact(label="Admins", value=", ".join(customer.admins) or "none", source="lookup_customer"))
    if customer.users_without_reporting:
        f.append(AccountFact(label="Users without Reporting permission",
                             value=f"{len(customer.users_without_reporting)}: " + ", ".join(customer.users_without_reporting),
                             source="lookup_customer"))
    for inv in sub.invoices_this_period:
        f.append(AccountFact(label=f"Invoice {inv.number}", value=f"{inv.kind} · {inv.amount} · {inv.days_ago}d ago · {inv.status}",
                             source="get_subscription"))
    for con in customer.connectors:
        status = con.get("status")
        detail = f"{status}" + (f" ({con['last_error']})" if con.get("last_error") else "")
        if con.get("last_success_hours_ago") is not None:
            detail += f", last success {con['last_success_hours_ago']}h ago"
        f.append(AccountFact(label=f"Connector {con.get('name')}", value=detail, source="lookup_customer"))
    if customer.foreign_emails_ignored:
        f.append(AccountFact(label="Other accounts mentioned (not accessed)",
                             value=", ".join(customer.foreign_emails_ignored), source="lookup_customer"))
    open_t = [t for t in tickets.tickets if t.status != "solved"]
    f.append(AccountFact(label="Existing tickets", value=f"{len(tickets.tickets)} recent, {len(open_t)} open"
                         + (": " + ", ".join(f"{t.number} {t.subject}" for t in open_t[:3]) if open_t else ""),
                         source="get_existing_tickets"))
    return f


def validate_citations(db: Session, req: SupportRequest, draft, passages, actor: str) -> list[Citation]:
    """A citation is kept only if its chunk was retrieved for *this* request.
    (This checks citation existence/provenance, not whether the passage supports the claim.)"""
    by_id = {p.chunk_id: p for p in passages}
    out: list[Citation] = []
    for ref in draft.citations:
        p = by_id.get(ref.chunk_id)
        if p is None:
            audit.record(db, workspace_id=req.workspace_id, actor=actor, event="citation.rejected",
                         request_id=req.id, demo_session_id=req.demo_session_id,
                         summary={"chunk_id": str(ref.chunk_id)},
                         error="Cited chunk was not retrieved for this request.")
            continue
        if any(c.chunk_id == p.chunk_id for c in out):
            continue
        out.append(Citation(chunk_id=p.chunk_id, document_id=p.document_id, document_version_id=p.document_version_id,
                            version=p.version, doc_slug=p.doc_slug, doc_title=p.doc_title, section=p.section,
                            claim=ref.claim, excerpt=p.text[:280]))
    return out


def apply_rules(content: ProposalContent, hits) -> ProposalContent:
    """Escalation rules override the model: if a rule requires escalation, the proposal escalates
    to the rule's group/priority regardless of what was drafted."""
    for rule, _hit in hits:
        o = rule.outcome
        if o.get("next_action") != "escalate":
            continue
        content.next_action = "escalate"
        content.priority = o.get("priority", content.priority)
        content.escalation_reason = content.escalation_reason or rule.description
        ta = content.ticket_action
        if ta.type != "create_ticket":
            content.ticket_action = TicketAction(
                type="create_ticket", subject=f"Escalation: {content.summary[:150]}",
                body=f"{content.summary}\n\nRule: {rule.name}.", priority=o.get("priority"),
                group=o.get("group"), status="open")
        else:
            ta.group, ta.priority = o.get("group"), o.get("priority")
    return content


def save_version(db: Session, proposal: Proposal, version: int, content: ProposalContent, author: str,
                 passages=None, edit_note: str | None = None, evidence_from: ProposalVersion | None = None) -> ProposalVersion:
    pv = ProposalVersion(workspace_id=proposal.workspace_id, proposal_id=proposal.id, version=version,
                         content=content.model_dump(mode="json"), action_hash=action_hash(content),
                         author=author, edit_note=edit_note)
    db.add(pv)
    db.flush()
    cited = {c.chunk_id for c in content.citations}
    if passages is not None:
        for p in passages:
            db.add(ProposalEvidence(workspace_id=proposal.workspace_id, proposal_version_id=pv.id,
                                    document_version_id=p.document_version_id, chunk_id=p.chunk_id,
                                    cited=p.chunk_id in cited, score=p.score))
    elif evidence_from is not None:  # edits keep the evidence of the version they were based on
        for e in db.query(ProposalEvidence).filter(ProposalEvidence.proposal_version_id == evidence_from.id):
            db.add(ProposalEvidence(workspace_id=e.workspace_id, proposal_version_id=pv.id,
                                    document_version_id=e.document_version_id, chunk_id=e.chunk_id,
                                    cited=e.cited, score=e.score))
    proposal.current_version = version
    return pv


@dataclass
class Gathered:
    """Everything the server needs to assemble a proposal, however the provider produced it."""
    cls: Classification
    customer: object
    sub: object
    tickets: object
    passages: list
    hits: list
    draft: object
    usage: Usage


class _SideExit(Exception):
    """The request left the pipeline through 'unsupported' (already transitioned)."""

    def __init__(self, usage: Usage | None = None):
        super().__init__()
        self.usage = usage


def _side_exit(db: Session, req: SupportRequest, actor: str, reason: str, usage: Usage | None = None):
    transition(db, req, "unsupported", actor, reason)
    raise _SideExit(usage)


def _run_stepwise(db: Session, req: SupportRequest, actor: str, provider) -> Gathered:
    """Demo path: the server calls the tools; the provider classifies and drafts."""
    ai = f"ai:{provider.name}"
    try:
        cls = _timed_ai(db, req, provider, "classify", lambda: provider.classify(req.subject, req.body))
    except UnsupportedInDemo as exc:
        _side_exit(db, req, actor, str(exc))
    req.category, req.priority = cls.category, cls.priority
    if cls.category == "unsupported":
        _side_exit(db, req, actor, "Outside supported categories; needs human handling.")
    transition(db, req, "classified", ai, cls.summary)
    if req.customer_id is None:
        _side_exit(db, req, actor, "No authorized customer record for this request.")
    ctx = tool_context(db, req, actor)
    customer = call_tool(ctx, "lookup_customer", {"mentioned_emails": cls.mentioned_emails})
    sub = call_tool(ctx, "get_subscription", {})
    tickets = call_tool(ctx, "get_existing_tickets", {"include_closed": True, "limit": 10})
    transition(db, req, "context_resolved", actor)
    passages, seen = [], set()
    for q in cls.search_queries:
        res = call_tool(ctx, "search_knowledge_base", {"query": q, "top_k": default_top_k()})
        for p in res.passages:
            if p.chunk_id not in seen:
                seen.add(p.chunk_id)
                passages.append(p)
    transition(db, req, "retrieved", actor, f"{len(passages)} passages")
    hits = rules.evaluate(db, req.workspace_id, category=cls.category, text=f"{req.subject}\n{req.body}", plan=sub.plan)
    inp = SynthesisInput(subject=req.subject, body=req.body, classification=cls, customer=customer,
                         subscription=sub, tickets=tickets.tickets, passages=passages,
                         rule_hits=[h for _, h in hits])
    draft = _timed_ai(db, req, provider, "synthesize", lambda: provider.synthesize(inp))
    return Gathered(cls, customer, sub, tickets, passages, hits, draft, Usage(model=None))


def _run_agentic(db: Session, req: SupportRequest, actor: str, provider) -> Gathered:
    """Live path: the model chooses which allowlisted tools to call (through ToolGate) and drafts.
    The server then fills any required context the model skipped, so account facts and escalation
    rules never depend on the model having asked for them."""
    if req.customer_id is None:
        _side_exit(db, req, actor, "No authorized customer record for this request.")
    ctx = tool_context(db, req, actor)
    started = time.perf_counter()
    try:
        result = provider.run_agent(ctx, req.subject, req.body)
    except ProviderError as exc:
        audit.record(db, workspace_id=req.workspace_id, actor=f"ai:{provider.name}", event="ai.run", request_id=req.id,
                     demo_session_id=req.demo_session_id, duration_ms=int((time.perf_counter() - started) * 1000),
                     summary={"provider": provider.label}, error=str(exc))
        raise
    u, cls = result.usage, result.classification
    audit.record(db, workspace_id=req.workspace_id, actor=f"ai:{provider.name}", event="ai.run", request_id=req.id,
                 demo_session_id=req.demo_session_id, duration_ms=int((time.perf_counter() - started) * 1000),
                 summary={"provider": provider.label, "model": u.model, "category": cls.category,
                          "next_action": result.draft.next_action, "tool_steps": u.tool_steps,
                          "api_calls": u.api_calls, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                          "citations": len(result.draft.citations), "blocked": len(result.security_flags)})
    req.category, req.priority = cls.category, cls.priority
    if cls.category == "unsupported":
        _side_exit(db, req, actor, "Outside supported categories; needs human handling.", u)
    transition(db, req, "classified", f"ai:{provider.name}", cls.summary)
    customer = result.customer or call_tool(ctx, "lookup_customer", {"mentioned_emails": cls.mentioned_emails})
    sub = result.subscription or call_tool(ctx, "get_subscription", {})
    tickets = (TicketList(tickets=result.tickets) if result.tickets is not None
               else call_tool(ctx, "get_existing_tickets", {"include_closed": True, "limit": 10}))
    transition(db, req, "context_resolved", actor)
    transition(db, req, "retrieved", actor, f"{len(result.passages)} passages from model-chosen searches")
    hits = rules.evaluate(db, req.workspace_id, category=cls.category, text=f"{req.subject}\n{req.body}", plan=sub.plan)
    return Gathered(cls, customer, sub, tickets, result.passages, hits, result.draft, u)


def _usage_dict(provider, usage: Usage, latency_ms: int) -> dict:
    return {"provider": "simulated" if provider.simulated else "live", "label": provider.label,
            "model": usage.model, "latency_ms": latency_ms, "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens, "cache_read_input_tokens": usage.cache_read_input_tokens,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens, "api_calls": usage.api_calls,
            "tool_steps": usage.tool_steps, "retries": usage.retries}


def _finish_run(run: AiRun, status: str, usage: Usage | None, started: float, error: str | None = None) -> None:
    run.status, run.error = status, (error[:2000] if error else None)
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    if usage is not None:
        run.model = usage.model or run.model
        run.input_tokens, run.output_tokens = usage.input_tokens, usage.output_tokens
        run.cache_read_input_tokens = usage.cache_read_input_tokens
        run.cache_creation_input_tokens = usage.cache_creation_input_tokens
        run.api_calls, run.tool_steps = usage.api_calls, usage.tool_steps


def run_request(db: Session, req: SupportRequest, actor: str, live: bool = False) -> SupportRequest:
    """Drive a request from 'received' to 'awaiting_review' (or a side exit). Commits.
    `live` selects the live provider; callers decide it from the actor (providers.live_for)."""
    if req.state != "received":
        raise InvalidTransition(f"Request must be 'received' to run (is '{req.state}').")
    audit.record(db, workspace_id=req.workspace_id, actor=actor, event="workflow.started",
                 request_id=req.id, demo_session_id=req.demo_session_id, summary={"live": live})
    started = time.perf_counter()
    run = AiRun(workspace_id=req.workspace_id, demo_session_id=req.demo_session_id, request_id=req.id, actor=actor,
                provider="live" if live else "simulated", status="running",
                model=get_settings().live_model if live else None)
    db.add(run)
    if live:
        db.commit()  # make the in-flight live run visible to rate limiting right away
    try:
        provider = get_provider(live)
    except ProviderError as exc:
        _finish_run(run, "error", None, started, str(exc))
        transition(db, req, "error", actor, str(exc))
        db.commit()
        return req
    ai = f"ai:{provider.name}"
    try:
        g = (_run_agentic if provider.agentic else _run_stepwise)(db, req, actor, provider)
        cls, hits = g.cls, g.hits

        # Server-side validation and assembly (identical for simulated and live output).
        citations = validate_citations(db, req, g.draft, g.passages, actor)
        content = ProposalContent(
            summary=cls.summary, category=cls.category, priority=cls.priority, justification=cls.justification,
            next_action=g.draft.next_action, account_facts=account_facts(g.customer, g.sub, g.tickets),
            draft_reply=g.draft.draft_reply, citations=citations, ticket_action=g.draft.ticket_action,
            missing_info=g.draft.missing_info, escalation_reason=g.draft.escalation_reason,
            rule_hits=[h for _, h in hits], risk_flags=list(cls.risk_flags),
            provider_label=provider.label, simulated=provider.simulated,
        )
        if not citations and content.next_action == "resolve":
            content.next_action = "escalate"
            content.escalation_reason = "No supporting documentation was retrieved; a human must review."
        content = apply_rules(content, hits)
        req.priority = content.priority
        checked = call_tool(tool_context(db, req, actor), "propose_ticket_action",
                            content.ticket_action.model_dump(mode="json"))
        if not checked.valid:
            raise ToolError("Proposed ticket action failed validation: " + "; ".join(checked.problems))

        _finish_run(run, "succeeded", g.usage, started)
        proposal = Proposal(workspace_id=req.workspace_id, request_id=req.id, provider=provider.label, status="open",
                            usage=_usage_dict(provider, g.usage, run.latency_ms))
        db.add(proposal)
        db.flush()
        save_version(db, proposal, 1, content, ai, passages=g.passages)
        transition(db, req, "awaiting_review", actor, f"Proposal v1: {content.next_action}")
        audit.record(db, workspace_id=req.workspace_id, actor=ai, event="proposal.created", request_id=req.id,
                     demo_session_id=req.demo_session_id,
                     summary={"version": 1, "next_action": content.next_action, "citations": len(citations),
                              "ticket_action": content.ticket_action.type,
                              "rule_hits": [h.key for _, h in hits]})
        db.commit()
    except _SideExit as exit_:
        _finish_run(run, "succeeded", exit_.usage, started)
        db.commit()
    except (ToolError, ProviderError, InvalidTransition) as exc:
        _finish_run(run, "error", getattr(exc, "usage", None), started, str(exc))
        req.state, req.state_reason = "error", str(exc)
        audit.record(db, workspace_id=req.workspace_id, actor=actor, event="workflow.error", request_id=req.id,
                     demo_session_id=req.demo_session_id, error=str(exc))
        db.commit()
    return req


def reprocess(db: Session, req: SupportRequest, actor: str, live: bool = False) -> SupportRequest:
    """Explicit re-run for rejected/stale/error/unsupported requests: closes old proposals, starts fresh."""
    transition(db, req, "received", actor, "Reprocess requested")
    db.query(Proposal).filter(Proposal.request_id == req.id, Proposal.status == "open").update({"status": "closed"})
    db.flush()
    return run_request(db, req, actor, live=live)
