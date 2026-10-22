"""Reviewer-only AI status: mode, model, whether a key is configured (never the key), budget and limits."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import limits
from ..config import get_settings
from ..context import Actor, require_reviewer
from ..db import get_db
from ..providers.live import label_for

router = APIRouter(prefix="/api/w/{ws}")


@router.get("/ai/status")
def ai_status(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    s = get_settings()
    used = limits.usage_this_month(db)
    live_used = used["live"]["total_tokens"]
    pricing = None
    if s.live_price_input_per_mtok is not None and s.live_price_output_per_mtok is not None:
        pricing = {"input_per_mtok_usd": s.live_price_input_per_mtok, "output_per_mtok_usd": s.live_price_output_per_mtok,
                   "source": "LIVE_PRICE_* environment variables (operator-configured)"}
    return {
        "mode": s.ai_mode,
        "provider_label": label_for(s.live_model) if s.ai_mode == "live" else "Simulated AI — demo mode",
        "model": s.live_model,
        "effort": s.live_effort,
        "refusal_fallback": s.live_refusal_fallback,
        "key_configured": bool(s.anthropic_api_key),  # never the key itself
        "live_for_visitors": s.live_allow_visitors,
        "budget": {
            "monthly_token_budget": s.live_monthly_token_budget,
            "tokens_used": live_used,
            "tokens_remaining": max(0, s.live_monthly_token_budget - live_used),
            "monthly_usd_budget": s.live_monthly_usd_budget if pricing else None,
            "cost_usd": used["live"]["cost_usd"],
            "pricing": pricing,
            "period_start": used["since"],
        },
        "usage_this_month": {"live": used["live"], "simulated": used["simulated"]},
        "limits": {
            "max_request_chars": s.max_request_chars,
            "max_upload_bytes": s.max_upload_bytes,
            "max_output_tokens_per_call": s.live_max_output_tokens,
            "max_tool_steps": s.live_max_tool_steps,
            "max_tokens_per_request": s.live_max_tokens_per_request,
            "call_timeout_s": s.live_call_timeout_s,
            "max_retries": s.live_max_retries,
            "rate_per_reviewer_per_min": s.live_rate_per_reviewer_per_min,
            "rate_global_per_min": s.live_rate_global_per_min,
            "max_concurrency": s.live_max_concurrency,
            "active_live_calls": limits.active_live_calls(),
        },
    }
