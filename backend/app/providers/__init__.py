from ..config import get_settings
from .base import AgentResult, AIProvider, ProviderError, SynthesisInput, UnsupportedInDemo, Usage

__all__ = ["AIProvider", "AgentResult", "ProviderError", "SynthesisInput", "UnsupportedInDemo", "Usage",
           "get_provider", "live_for"]


def live_for(is_reviewer: bool) -> bool:
    """Whether a caller's requests use the live model. Public visitors never do unless
    LIVE_ALLOW_VISITORS is deliberately enabled; they keep the simulated demo."""
    s = get_settings()
    return s.ai_mode == "live" and (is_reviewer or s.live_allow_visitors)


def get_provider(live: bool = False) -> AIProvider:
    """Live failures raise ProviderError (e.g. missing key); they are never replaced by simulation."""
    if not live:
        from .simulated import SimulatedProvider

        return SimulatedProvider()
    from .live import LiveProvider

    return LiveProvider()
