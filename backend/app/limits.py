"""Usage and spending controls for live model calls (SPEC §12).

- Input size: request text (subject + body) is capped before any live call.
- Rate limits: live runs per reviewer and globally per rolling minute, counted from `ai_runs` rows
  in Postgres (a run row is committed before the model is called, so in-flight runs count).
- Budget: input + output tokens of live runs this calendar month (UTC). An optional USD budget is
  enforced only when both per-token prices are configured; prices are never assumed.
- Concurrency: an in-process counter. It limits one API process; running several API instances
  would need a shared limiter (documented single-instance limitation, docs/DECISIONS.md D19).

Every limit raises LimitExceeded, which the API turns into a 429/413 with a plain explanation.
No request row is created when a limit is hit.
"""
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import AiRun


class LimitExceeded(Exception):
    def __init__(self, detail: str, kind: str, status_code: int = 429):
        super().__init__(detail)
        self.detail, self.kind, self.status_code = detail, kind, status_code


_lock = threading.Lock()
_active = 0


def active_live_calls() -> int:
    return _active


@contextmanager
def live_slot():
    """Hold one of LIVE_MAX_CONCURRENCY live slots for the duration of a live run (non-blocking)."""
    global _active
    limit = get_settings().live_max_concurrency
    with _lock:
        if _active >= limit:
            raise LimitExceeded(f"Live mode is busy: {_active} live request(s) already running "
                                f"(limit {limit}). Try again in a moment.", "concurrency")
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1


def check_input(subject: str, body: str, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    size = len(subject) + len(body)
    if size > s.max_request_chars:
        raise LimitExceeded(f"Request text is {size} characters; live mode accepts at most "
                            f"{s.max_request_chars}. Shorten the message.", "input_size", 413)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def cost_usd(input_tokens: int, output_tokens: int, settings: Settings | None = None, *,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float | None:
    """Estimate from the configured prices only. Cache reads and writes are priced as multiples of the
    input price (LIVE_PRICE_CACHE_*_MULTIPLIER). Tiered long-prompt pricing is not modelled."""
    s = settings or get_settings()
    if s.live_price_input_per_mtok is None or s.live_price_output_per_mtok is None:
        return None
    p_in = s.live_price_input_per_mtok / 1e6
    return round(input_tokens * p_in
                 + cache_read_tokens * p_in * s.live_price_cache_read_multiplier
                 + cache_write_tokens * p_in * s.live_price_cache_write_multiplier
                 + output_tokens / 1e6 * s.live_price_output_per_mtok, 4)


def usage_this_month(db: Session) -> dict:
    since = month_start()
    out = {}
    for provider in ("live", "simulated"):
        runs, inp, cread, cwrite, outp, errors = db.execute(select(
            func.count(AiRun.id), func.coalesce(func.sum(AiRun.input_tokens), 0),
            func.coalesce(func.sum(AiRun.cache_read_input_tokens), 0),
            func.coalesce(func.sum(AiRun.cache_creation_input_tokens), 0),
            func.coalesce(func.sum(AiRun.output_tokens), 0),
            func.count(AiRun.id).filter(AiRun.status == "error"),
        ).where(AiRun.provider == provider, AiRun.created_at >= since)).one()
        total_in = int(inp) + int(cread) + int(cwrite)
        out[provider] = {"runs": runs, "errors": errors, "input_tokens": total_in, "uncached_input_tokens": int(inp),
                         "cache_read_input_tokens": int(cread), "cache_creation_input_tokens": int(cwrite),
                         "output_tokens": int(outp), "total_tokens": total_in + int(outp)}
    lv = out["live"]
    lv["cost_usd"] = cost_usd(lv["uncached_input_tokens"], lv["output_tokens"],
                              cache_read_tokens=lv["cache_read_input_tokens"],
                              cache_write_tokens=lv["cache_creation_input_tokens"])
    out["since"] = since.isoformat()
    return out


def _recent_live_runs(db: Session, actor_label: str | None) -> int:
    q = select(func.count(AiRun.id)).where(AiRun.provider == "live",
                                           AiRun.created_at >= datetime.now(timezone.utc) - timedelta(seconds=60))
    if actor_label is not None:
        q = q.where(AiRun.actor == actor_label)
    return db.scalar(q) or 0


def preflight(db: Session, actor_label: str) -> None:
    """Rate limits and budget, checked before a live run is started."""
    s = get_settings()
    mine = _recent_live_runs(db, actor_label)
    if mine >= s.live_rate_per_reviewer_per_min:
        raise LimitExceeded(f"Live rate limit reached: {s.live_rate_per_reviewer_per_min} live request(s) per "
                            "minute per reviewer. Wait a minute and try again.", "rate_reviewer")
    total = _recent_live_runs(db, None)
    if total >= s.live_rate_global_per_min:
        raise LimitExceeded(f"Live rate limit reached: {s.live_rate_global_per_min} live request(s) per minute "
                            "across all reviewers. Wait a minute and try again.", "rate_global")
    used = usage_this_month(db)["live"]
    if used["total_tokens"] >= s.live_monthly_token_budget:
        raise LimitExceeded(f"Live usage budget exhausted: {used['total_tokens']:,} of "
                            f"{s.live_monthly_token_budget:,} tokens used this month. Raise "
                            "LIVE_MONTHLY_TOKEN_BUDGET deliberately or switch to demo mode.", "budget_tokens")
    if s.live_monthly_usd_budget is not None and used["cost_usd"] is not None \
            and used["cost_usd"] >= s.live_monthly_usd_budget:
        raise LimitExceeded(f"Live spending budget exhausted: ${used['cost_usd']:.2f} of "
                            f"${s.live_monthly_usd_budget:.2f} this month (at the configured prices).",
                            "budget_usd")
