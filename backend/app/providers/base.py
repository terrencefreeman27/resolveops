"""AI provider interface. The provider interprets language and drafts proposals; it never
authorizes, validates, approves or executes anything — application code does that."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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


class AIProvider(ABC):
    name: str
    label: str
    simulated: bool

    @abstractmethod
    def classify(self, subject: str, body: str) -> Classification: ...

    @abstractmethod
    def synthesize(self, inp: SynthesisInput) -> ProposalDraft: ...
