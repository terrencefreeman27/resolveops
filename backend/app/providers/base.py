"""AI provider interface. The provider interprets language and drafts proposals; it never
authorizes, validates, approves or executes anything — application code does that."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..schemas import (
    Classification,
    CustomerFacts,
    Passage,
    ProposalDraft,
    RuleHit,
    SubscriptionFacts,
    TicketFact,
)


class ProviderError(Exception):
    """A provider failed or is misconfigured. Surfaced to the user; never replaced by simulated output."""


class UnsupportedInDemo(Exception):
    """Demo mode only handles the seeded scenarios."""


@dataclass
class SynthesisInput:
    subject: str
    body: str
    classification: Classification
    customer: CustomerFacts
    subscription: SubscriptionFacts
    tickets: list[TicketFact]
    passages: list[Passage]
    rule_hits: list[RuleHit] = field(default_factory=list)


@dataclass
class Usage:
    """Provider usage for one request, taken from the API's usage fields (zeros for simulated)."""
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    api_calls: int = 0
    tool_steps: int = 0
    retries: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class AgentResult:
    """What an agentic (live) provider returns: its interpretation and draft, plus every validated
    tool output it obtained. Account facts and evidence are later built from these tool outputs by
    the server — never from the model's own text."""
    classification: Classification
    draft: ProposalDraft
    customer: CustomerFacts | None
    subscription: SubscriptionFacts | None
    tickets: list[TicketFact] | None
    passages: list[Passage]
    security_flags: list[str]
    usage: Usage


class AIProvider(ABC):
    name: str
    label: str
    simulated: bool
    agentic: bool = False  # True: the provider runs its own tool loop via run_agent()

    @abstractmethod
    def classify(self, subject: str, body: str) -> Classification: ...

    @abstractmethod
    def synthesize(self, inp: SynthesisInput) -> ProposalDraft: ...

    def run_agent(self, ctx: Any, subject: str, body: str) -> AgentResult:  # pragma: no cover - live only
        raise ProviderError(f"{self.label} does not run a tool loop.")
