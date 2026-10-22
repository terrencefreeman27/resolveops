"""Live smoke test against the real Anthropic API.

Run deliberately:   docker compose exec api pytest -m live -q
Skipped unless ANTHROPIC_API_KEY is set in the API container's environment. It spends real tokens
(four requests, each a short tool loop) and is excluded from the default test run.

It checks the end-to-end contract, not exact wording: each run reaches awaiting_review with a
live-labelled proposal whose citations passed server validation, and usage was recorded.
"""
import os

import pytest

from tests.conftest import WS, customer_id

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")]


@pytest.fixture
def real_live(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "ai_mode", "live")
    monkeypatch.setattr(s, "anthropic_api_key", os.environ["ANTHROPIC_API_KEY"])
    return s


def check(d: dict, expect_action: str | None = None) -> None:
    assert d["state"] == "awaiting_review", d["state_reason"]
    p = d["proposal"]
    c = p["version"]["content"]
    assert c["simulated"] is False and c["provider_label"].startswith("Live — Claude")
    assert p["usage"]["input_tokens"] > 0 and p["usage"]["output_tokens"] > 0 and p["usage"]["tool_steps"] >= 1
    assert all(x["doc_slug"] for x in c["citations"])  # only citations that survived validation remain
    if expect_action:
        assert c["next_action"] == expect_action


@pytest.mark.parametrize("key,action", [
    ("access_reporting_after_upgrade", None),
    ("billing_charged_twice", None),
    ("connector_outage", "escalate"),  # enforced by the escalation rule regardless of the model
])
def test_seeded_scenarios_live(real_live, reviewer, key, action):
    r = reviewer.post(f"{WS}/scenarios/{key}/run")
    assert r.status_code == 200, r.text
    check(r.json(), action)


def test_new_free_text_request_live(real_live, reviewer):
    r = reviewer.post(f"{WS}/requests", json={
        "subject": "Seat count question",
        "body": "How many seats do we have left, and who on our team can add more?",
        "customer_id": customer_id(reviewer, "Brightline Logistics")})
    assert r.status_code == 200, r.text
    check(r.json())
