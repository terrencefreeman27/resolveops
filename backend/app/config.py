"""Application settings, read from environment variables only."""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://resolveops:resolveops@db:5432/resolveops"
    ai_mode: Literal["demo", "live"] = "demo"
    anthropic_api_key: str = ""  # never sent to the frontend, never logged

    seed_reviewer_email: str = "reviewer@northstar.example"
    seed_reviewer_password: str = "northstar-demo"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    retrieval_top_k: int = 6
    # Evidence check (evidence.py): passages scoring below this cosine similarity are not treated as
    # supporting evidence. A workspace can override it with settings.retrieval_min_score.
    # Calibrated on the seeded data (bge-small): answered scenarios score 0.79-0.89, the undocumented
    # Peppol question 0.69. See docs/DECISIONS.md D25.
    retrieval_min_score: float = 0.72

    max_request_chars: int = 4000
    session_ttl_hours: int = 12
    demo_session_ttl_hours: int = 48
    cookie_secure: bool = False  # set true behind HTTPS

    execution_max_attempts: int = 3
    execution_attempt_timeout_s: float = 5.0

    # --- live mode (Claude). See docs/DECISIONS.md D16-D20 and README "Live mode". ---
    live_model: str = "claude-haiku-5-5"
    live_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    live_refusal_fallback: bool = True  # server-side fallback on safety refusals; only sent to models that support it (see FALLBACK_MODELS)
    live_allow_visitors: bool = False  # public visitors never use live mode unless deliberately enabled
    live_max_output_tokens: int = 8000  # per model call (includes adaptive thinking)
    live_max_tool_steps: int = 6  # model turns that may call tools, per request
    live_max_tokens_per_request: int = 150_000  # input + output summed over the tool loop
    live_call_timeout_s: float = 120.0
    live_max_retries: int = 2  # retries for 429 / 5xx / overloaded / timeouts (non-retryable errors fail at once)
    live_retry_base_delay_s: float = 1.0
    live_retry_max_delay_s: float = 8.0
    live_rate_per_reviewer_per_min: int = 5
    live_rate_global_per_min: int = 20
    live_max_concurrency: int = 2  # in-process limit (single API instance)
    live_monthly_token_budget: int = 2_000_000  # input + output tokens per calendar month (UTC); 0 = no live calls
    # Optional USD budget: only used when BOTH prices are set. Never assumed.
    live_price_input_per_mtok: float | None = None
    live_price_output_per_mtok: float | None = None
    live_monthly_usd_budget: float | None = None
    max_upload_bytes: int = 200_000  # per imported document (.md / .txt)
    max_documents_per_workspace: int = 40
    max_workspaces_per_reviewer: int = 10

    # --- optional GitHub Issues adapter (M4). See docs/DECISIONS.md D28-D30 and README. ---
    # The destination is server config only: the base URL is fixed in adapters/github.py and the
    # repository must be both GITHUB_ISSUES_REPO and listed in GITHUB_ALLOWED_REPOS.
    github_adapter_enabled: bool = False
    github_token: SecretStr = SecretStr("")  # never logged, returned, prompted or sent to the frontend
    github_issues_repo: str = ""  # owner/name
    github_allowed_repos: str = ""  # comma-separated owner/name list
    github_labels: str = ""  # optional, comma-separated; needs push access or GitHub silently drops them
    github_timeout_s: float = 10.0  # per HTTP request
    github_max_attempts: int = 3  # per HTTP call (create or lookup), including the first
    github_retry_base_delay_s: float = 1.0
    github_max_wait_s: float = 10.0  # longest Retry-After / rate-limit wait honoured inline


@lru_cache
def get_settings() -> Settings:
    return Settings()
