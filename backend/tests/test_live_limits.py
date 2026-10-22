"""Usage and spending controls for live mode: size, rate, budget, concurrency, usage records."""
import json

from sqlalchemy import func, select

from app import limits
from app.models import AiRun, SupportRequest
from tests.conftest import WS, customer_id
from tests.live_fakes import final_turn, tool_turn

FINAL = {"classification": {"category": "access", "priority": "normal", "justification": "j", "summary": "s",
                            "mentioned_emails": [], "risk_flags": []},
         "proposal": {"next_action": "clarify", "draft_reply": "Which users?", "citations": [],
                      "ticket_action": {"type": "none", "subject": None, "body": None, "priority": None, "group": None,
                                        "status": None, "ticket_id": None},
                      "missing_info": ["Which users"], "escalation_reason": None}}


def steps():
    return [tool_turn(("get_subscription", {})), final_turn(FINAL)]


def run(reviewer):
    return reviewer.post(f"{WS}/scenarios/access_reporting_after_upgrade/run")


def request_count(db) -> int:
    db.expire_all()
    return db.scalar(select(func.count(SupportRequest.id)))


def recent_live(db, actor=None) -> int:
    db.expire_all()
    return limits._recent_live_runs(db, actor)


def test_input_size_limit(live, reviewer, db):
    live.set(max_request_chars=40)
    live.script([])
    before = request_count(db)
    r = reviewer.post(f"{WS}/requests", json={"subject": "Long", "body": "x" * 60,
                                              "customer_id": customer_id(reviewer, "Brightline Logistics")})
    assert r.status_code == 413 and "at most 40" in r.json()["detail"] and r.json()["limit"] == "input_size"
    assert request_count(db) == before and live.client.calls == []


def test_rate_limit_per_reviewer(live, reviewer, db):
    live.set(live_rate_per_reviewer_per_min=recent_live(db, "reviewer:reviewer@northstar.example") + 1)
    live.script(steps())
    assert run(reviewer).status_code == 200
    before = request_count(db)
    r = run(reviewer)
    assert r.status_code == 429 and r.json()["limit"] == "rate_reviewer" and "per minute" in r.json()["detail"]
    assert r.headers.get("retry-after") == "60"
    assert request_count(db) == before  # nothing was created


def test_rate_limit_global(live, reviewer, db):
    live.set(live_rate_global_per_min=recent_live(db))
    live.script([])
    r = run(reviewer)
    assert r.status_code == 429 and r.json()["limit"] == "rate_global"


def test_token_budget(live, reviewer, db):
    live.script(steps())
    assert run(reviewer).status_code == 200  # ensure some live usage exists this month
    used = limits.usage_this_month(db)["live"]["total_tokens"]
    live.set(live_monthly_token_budget=used)
    r = run(reviewer)
    assert r.status_code == 429 and r.json()["limit"] == "budget_tokens" and "exhausted" in r.json()["detail"]


def test_usd_budget_only_when_prices_configured(live, reviewer, db):
    live.script(steps() * 2)
    live.set(live_monthly_usd_budget=0.0)  # a USD budget without prices is ignored (prices never assumed)
    assert run(reviewer).status_code == 200
    live.set(live_price_input_per_mtok=1.0, live_price_output_per_mtok=1.0)
    r = run(reviewer)
    assert r.status_code == 429 and r.json()["limit"] == "budget_usd" and "configured prices" in r.json()["detail"]


def test_concurrency_limit(live, reviewer):
    live.set(live_max_concurrency=1)
    live.script([])
    with limits.live_slot():
        r = run(reviewer)
    assert r.status_code == 429 and r.json()["limit"] == "concurrency" and "busy" in r.json()["detail"]
    live.script(steps())
    assert run(reviewer).status_code == 200  # slot released


def test_usage_recorded_and_simulated_kept_separate(live, reviewer, visitor, db):
    live.script(steps())
    d = run(reviewer).json()
    u = d["proposal"]["usage"]
    assert u["provider"] == "live" and u["input_tokens"] == 1500 + 4000 and u["output_tokens"] == 120 + 600
    assert u["tool_steps"] == 1 and u["model"] == "claude-opus-5-5"
    v = visitor.post(f"{WS}/scenarios/access_reporting_after_upgrade/run").json()
    vu = v["proposal"]["usage"]
    assert vu["provider"] == "simulated" and vu["input_tokens"] == 0 and vu["model"] is None
    row = db.scalar(select(AiRun).where(AiRun.request_id == v["id"]))
    assert row.provider == "simulated" and row.status == "succeeded"


def test_status_panel_shows_config_never_the_key(live, reviewer, visitor):
    live.script(steps())
    run(reviewer)
    s = reviewer.get(f"{WS}/ai/status")
    assert s.status_code == 200
    body = s.json()
    assert body["mode"] == "live" and body["model"] == "claude-opus-5-5" and body["key_configured"] is True
    assert body["budget"]["tokens_used"] > 0 and body["budget"]["pricing"] is None
    assert body["limits"]["max_tool_steps"] == live.settings.live_max_tool_steps
    assert body["usage_this_month"]["live"]["runs"] >= 1
    assert live.settings.anthropic_api_key not in s.text
    assert "sk-ant" not in json.dumps(visitor.get("/api/meta").json())
