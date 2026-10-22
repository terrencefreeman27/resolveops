from ..config import get_settings
from .base import AIProvider, ProviderError, SynthesisInput, UnsupportedInDemo

__all__ = ["AIProvider", "ProviderError", "SynthesisInput", "UnsupportedInDemo", "get_provider"]


def get_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_mode == "demo":
        from .simulated import SimulatedProvider

        return SimulatedProvider()
    # Live mode is Milestone 2. Fail loudly rather than silently simulating.
    if not settings.anthropic_api_key:
        raise ProviderError("Live mode is selected but ANTHROPIC_API_KEY is not set.")
    raise ProviderError("Live provider is not implemented yet (Milestone 2). Set AI_MODE=demo.")
