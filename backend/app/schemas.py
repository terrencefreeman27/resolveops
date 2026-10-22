"""Pydantic v2 schemas for tool I/O, AI provider output, and proposals.

Everything crossing the boundary between the AI provider, the tools and the database is
validated here. `extra="forbid"` means a provider cannot smuggle extra fields (such as a
customer_id or an "approved" flag) into a structured output.
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["access", "billing", "product_issue", "unsupported"]
Priority = Literal["low", "normal", "high", "urgent"]
NextAction = Literal["resolve", "clarify", "escalate"]
TicketActionType = Literal["none", "create_ticket", "add_note"]
TicketStatus = Literal["open", "pending_customer", "solved"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- tool arguments / outputs ---------------------------------------------------

class LookupCustomerArgs(Strict):
    mentioned_emails: list[str] = Field(default_factory=list, max_length=10)


class AccountUserFact(Strict):
    name: str
    email: str
    role: str
    has_reporting: bool


class CustomerFacts(Strict):
    customer_id: uuid.UUID
    account_ref: str
    company_name: str
    contact_name: str
    contact_email: str
    is_synthetic: bool
    users: list[AccountUserFact]
    admins: list[str]
    users_without_reporting: list[str]
    connectors: list[dict] = Field(default_factory=list)
    other_metadata: dict = Field(default_factory=dict)
    # Emails mentioned in the message that do NOT belong to the authorized customer.
    foreign_emails_ignored: list[str] = Field(default_factory=list)


class EmptyArgs(Strict):
    pass


class InvoiceFact(Strict):
    number: str
    kind: str
    description: str
    amount: str
    status: str
    issued_at: datetime
    days_ago: int


class SubscriptionFacts(Strict):
    plan: str
    status: str
    billing_cycle: str
    seats_purchased: int
    seats_used: int
    seats_available: int
    price_per_seat: str
    features: list[str]
    previous_plan: str | None
    plan_changed_at: datetime | None
    plan_changed_days_ago: int | None
    current_period_start: datetime
    current_period_end: datetime
    invoices_this_period: list[InvoiceFact]


class SearchKnowledgeBaseArgs(Strict):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=6, ge=1, le=10)


class Passage(Strict):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version: int
    doc_slug: str
    doc_title: str
    section: str
    text: str
    score: float


class SearchResults(Strict):
    passages: list[Passage]


class GetTicketsArgs(Strict):
    include_closed: bool = True
    limit: int = Field(default=10, ge=1, le=25)


class TicketFact(Strict):
    id: uuid.UUID
    number: str
    subject: str
    category: str
    priority: str
    status: str
    group: str
    created_days_ago: int


class TicketList(Strict):
    tickets: list[TicketFact]


class TicketAction(Strict):
    type: TicketActionType
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    priority: Priority | None = None
    group: str | None = Field(default=None, max_length=64)
    status: TicketStatus | None = None
    ticket_id: uuid.UUID | None = None  # for add_note


class ProposedTicketAction(Strict):
    action: TicketAction
    valid: bool
    problems: list[str]


# --- provider output ------------------------------------------------------------

class Classification(Strict):
    category: Category
    priority: Priority
    justification: str = Field(max_length=500)
    summary: str = Field(max_length=500)
    mentioned_emails: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(min_length=1, max_length=4)
    risk_flags: list[str] = Field(default_factory=list)


class CitationRef(Strict):
    chunk_id: uuid.UUID
    claim: str = Field(max_length=300)


class ProposalDraft(Strict):
    """What the AI provider is allowed to propose. Account facts are NOT part of this:
    the server attaches them from tool results."""
    next_action: NextAction
    draft_reply: str = Field(min_length=1, max_length=4000)
    citations: list[CitationRef] = Field(max_length=8)
    ticket_action: TicketAction
    missing_info: list[str] = Field(default_factory=list)
    escalation_reason: str | None = None


# --- stored proposal ------------------------------------------------------------

class AccountFact(Strict):
    label: str
    value: str
    source: str  # tool name


class Citation(Strict):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version: int
    doc_slug: str
    doc_title: str
    section: str
    claim: str
    excerpt: str


class RuleHit(Strict):
    key: str
    name: str
    effect: str


class ConflictValue(Strict):
    value: str
    document_id: uuid.UUID
    doc_title: str
    version: int
    section: str
    chunk_id: uuid.UUID


class PolicyConflict(Strict):
    key: str
    values: list[ConflictValue]


class EvidenceCheck(Strict):
    """Deterministic evidence assessment made by application code (evidence.py), not by the model."""
    status: Literal["sufficient", "insufficient", "conflicting"]
    threshold: float
    best_score: float | None
    relevant_passages: int
    conflicts: list[PolicyConflict] = Field(default_factory=list)
    effect: str | None = None  # what the check changed in the proposal, if anything


class ProposalContent(Strict):
    summary: str
    category: Category
    priority: Priority
    justification: str
    next_action: NextAction
    account_facts: list[AccountFact]
    draft_reply: str
    citations: list[Citation]
    ticket_action: TicketAction
    missing_info: list[str]
    escalation_reason: str | None
    rule_hits: list[RuleHit]
    risk_flags: list[str]
    provider_label: str
    simulated: bool
    evidence_check: EvidenceCheck | None = None  # absent on proposals created before Milestone 3


def action_hash(content: ProposalContent) -> str:
    """Hash of the parts of a proposal that approval authorizes."""
    payload = {
        "next_action": content.next_action,
        "draft_reply": content.draft_reply,
        "ticket_action": content.ticket_action.model_dump(mode="json"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# --- API inputs -----------------------------------------------------------------

class LoginIn(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class SubmitRequestIn(Strict):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    customer_id: uuid.UUID | None = None  # reviewers only; visitors/customers use a customer session


class CustomerSessionIn(Strict):
    customer_id: uuid.UUID


class EditProposalIn(Strict):
    base_version: int
    draft_reply: str | None = Field(default=None, min_length=1, max_length=4000)
    next_action: NextAction | None = None
    ticket_action: TicketAction | None = None
    note: str | None = Field(default=None, max_length=500)


class ApproveIn(Strict):
    proposal_version_id: uuid.UUID
    action_hash: str = Field(min_length=64, max_length=64)


class RejectIn(Strict):
    proposal_version_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)
