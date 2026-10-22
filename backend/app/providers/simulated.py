"""Deterministic simulated AI for demo mode — generic code, workspace-scoped data.

Fixtures are rows in `sim_fixtures` (one per seeded scenario per workspace), loaded by the seed from
`app/seed/<company>_fixtures.py`. This module contains no company-specific text or branches: it matches
the request body against the workspace's fixtures and renders the fixture's templates from the *tool
results* (customer, subscription, tickets) and from passages retrieval actually returned. So:

- account facts still drive the answer (e.g. which users hold which role);
- a citation is emitted only if retrieval returned that document section for this request;
- the same wording in two workspaces renders two different, workspace-specific answers.

Anything that is not a seeded scenario raises UnsupportedInDemo — demo mode never pretends a model
read free text.

Fixture synthesis format::

    {"variants": [
        {"when": {"plan_lacks_feature": "reporting"},          # optional; all conditions must hold
         "next_action": "resolve" | "clarify" | "escalate",
         "reply": "Hi {first_name}, ...",                       # str.format over the variables below
         "citations": [["doc-slug", "Section title prefix", "claim"], ...],
         "ticket_action": {"type": "create_ticket", "subject": "...", ...} | {"type": "none"}
                          | {"type": "add_note", "ticket_match": "saml", "body": "..."},
         "missing_info": ["..."], "escalation_reason": "..."},
        ...]}

Conditions: plan_lacks_feature, plan_has_feature, no_users_with_role, open_ticket_matching.
Variables: first_name, contact_name, company, account_ref, plan, previous_plan, billing_cycle,
seats_used, seats_purchased, seats_available, plan_change_when, admins, users_with_role[Role],
count_with_role[Role], invoice_lines, failing_connector, failing_connector_hours,
failing_connector_error, signature, workspace_name.
"""
import re
import string
from dataclasses import dataclass, field

from ..schemas import CitationRef, Classification, Passage, ProposalDraft, TicketAction
from .base import AIProvider, ProviderError, SynthesisInput, UnsupportedInDemo

LABEL = "Simulated AI — demo mode"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("—", "-")).strip().lower()


def names(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class _Lookup(dict):
    """users_with_role[Viewer] -> 'A, B and C'; missing roles render as empty / 0."""

    def __init__(self, data: dict, default):
        super().__init__(data)
        self._default = default

    def __missing__(self, key):
        return self._default


def variables(inp: SynthesisInput, profile: dict, workspace_name: str) -> dict:
    c, s = inp.customer, inp.subscription
    by_role: dict[str, list[str]] = {}
    for u in c.users:
        by_role.setdefault(u.role, []).append(u.name)
    days = s.plan_changed_days_ago
    failing = next((x for x in c.connectors if x.get("status") == "failing"), {})
    return {
        "first_name": c.contact_name.split()[0], "contact_name": c.contact_name, "company": c.company_name,
        "account_ref": c.account_ref, "plan": s.plan, "previous_plan": s.previous_plan or s.plan,
        "billing_cycle": s.billing_cycle, "seats_used": s.seats_used, "seats_purchased": s.seats_purchased,
        "seats_available": s.seats_available,
        "plan_change_when": "" if days is None else ("yesterday" if days in (0, 1) else f"{days} days ago"),
        "admins": names(c.admins),
        "users_with_role": _Lookup({r: names(v) for r, v in by_role.items()}, ""),
        "count_with_role": _Lookup({r: len(v) for r, v in by_role.items()}, 0),
        "invoice_lines": "\n".join(f"• {i.number} — {i.description}: {i.amount} ({i.days_ago} days ago)"
                                   for i in s.invoices_this_period),
        "failing_connector": failing.get("name", "your connector"),
        "failing_connector_hours": failing.get("last_success_hours_ago", "several"),
        "failing_connector_error": failing.get("last_error") or "an error",
        "signature": profile.get("support_signature") or f"{workspace_name} Support",
        "workspace_name": workspace_name,
    }


def render(template, vars_: dict):
    if template is None:
        return None
    try:
        return string.Formatter().vformat(template, (), vars_)
    except (KeyError, IndexError, ValueError) as exc:  # a broken fixture is a configuration error
        raise ProviderError(f"Simulated fixture template error: {exc!r}") from exc


def _open_ticket(inp: SynthesisInput, term: str):
    return next((t for t in inp.tickets if term.lower() in t.subject.lower() and t.status != "solved"), None)


def matches(when: dict | None, inp: SynthesisInput) -> bool:
    s, c = inp.subscription, inp.customer
    checks = {
        "plan_lacks_feature": lambda v: v not in s.features,
        "plan_has_feature": lambda v: v in s.features,
        "no_users_with_role": lambda v: not any(u.role == v for u in c.users),
        "open_ticket_matching": lambda v: _open_ticket(inp, v) is not None,
    }
    for key, value in (when or {}).items():
        if key not in checks:
            raise ProviderError(f"Unknown simulated fixture condition '{key}'.")
        if not checks[key](value):
            return False
    return True


def cite(passages: list[Passage], doc_slug: str, section_prefix: str, claim: str) -> CitationRef | None:
    """Cite a passage only if retrieval returned it for this request."""
    p = next((p for p in passages if p.doc_slug == doc_slug
              and p.section.lower().startswith(section_prefix.lower())), None)
    return CitationRef(chunk_id=p.chunk_id, claim=claim) if p else None


def ticket_action(spec: dict | None, inp: SynthesisInput, vars_: dict) -> TicketAction:
    spec = dict(spec or {"type": "none"})
    if spec.get("type") == "add_note":
        t = _open_ticket(inp, spec.pop("ticket_match", ""))
        if t is None:
            return TicketAction(type="none")
        spec["ticket_id"] = t.id
    return TicketAction(**{k: (render(v, vars_) if isinstance(v, str) and k != "type" else v)
                           for k, v in spec.items()})


@dataclass
class Fixture:
    key: str
    match_text: str
    classification: dict
    synthesis: dict = field(default_factory=dict)


class SimulatedProvider(AIProvider):
    name = "simulated"
    label = LABEL
    simulated = True

    def __init__(self, fixtures: list[Fixture] | None = None, profile: dict | None = None, workspace_name: str = ""):
        self._by_text = {normalize(f.match_text): f for f in (fixtures or [])}
        self.profile = profile or {}
        self.workspace_name = workspace_name

    def _fixture(self, body: str) -> Fixture:
        f = self._by_text.get(normalize(body))
        if f is None:
            raise UnsupportedInDemo(
                "Demo mode only handles the seeded scenarios. This message was not processed by any AI model. "
                "Run one of this workspace's demo scenarios, or have a signed-in reviewer process it in live mode.")
        return f

    def classify(self, subject: str, body: str) -> Classification:
        return Classification(**self._fixture(body).classification)

    def synthesize(self, inp: SynthesisInput) -> ProposalDraft:
        fx = self._fixture(inp.body)
        variant = next((v for v in fx.synthesis.get("variants", []) if matches(v.get("when"), inp)), None)
        if variant is None:
            raise ProviderError(f"Simulated fixture '{fx.key}' has no variant for this account.")
        vars_ = variables(inp, self.profile, self.workspace_name)
        refs = (cite(inp.passages, d, sec, render(claim, vars_)) for d, sec, claim in variant.get("citations", []))
        return ProposalDraft(
            next_action=variant["next_action"],
            draft_reply=render(variant["reply"], vars_),
            citations=[r for r in refs if r is not None],
            ticket_action=ticket_action(variant.get("ticket_action"), inp, vars_),
            missing_info=[render(m, vars_) for m in variant.get("missing_info", [])],
            escalation_reason=render(variant.get("escalation_reason"), vars_),
        )


def load_for_workspace(db, workspace_id) -> SimulatedProvider:
    """Build the simulated provider from the workspace's own fixture rows and profile."""
    from sqlalchemy import select

    from ..models import SimFixture, Workspace

    ws = db.get(Workspace, workspace_id)
    rows = db.scalars(select(SimFixture).where(SimFixture.workspace_id == workspace_id)).all()
    return SimulatedProvider([Fixture(r.key, r.match_text, r.classification, r.synthesis) for r in rows],
                             profile=ws.profile if ws else {}, workspace_name=ws.name if ws else "")
