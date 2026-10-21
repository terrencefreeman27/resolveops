"""Application settings, read from environment variables only."""
from functools import lru_cache
from typing import Literal

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

    max_request_chars: int = 4000
    session_ttl_hours: int = 12
    demo_session_ttl_hours: int = 48
    cookie_secure: bool = False  # set true behind HTTPS

    execution_max_attempts: int = 3
    execution_attempt_timeout_s: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
