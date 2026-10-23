"""Live provider behaviour with a fake Anthropic client: happy path, loop cap, retries, errors.
No test here touches the network or a real key."""
import json

import anthropic

from tests.conftest import FAKE_KEY, WS, customer_id
from tests.live_fakes import (api_error, final_turn, fixture_tokens, load_fixture, response, timeout_error,
                              tool_turn)

ALLOWLIST = {"lookup_customer", "get_subscription", "search_knowledge_base", "get_existing_tickets",
             "propose_ticket_action"}
SIMPLE_FINAL = {
    "classification": {"category": "access", "priority": "normal", "justification": "j", "summary": "s",
                       "mentioned_emails": [], "risk_flags": []},
    "proposal": {"next_action": "resolve", "draft_reply": "Hello", "citations": [],
                 "ticket_action": {"type": "none", "subject": None, "body": None, "priority": None, "group": None,
                                   "status": None, "ticket_id": None},
                 "missing_info": [], "escalation_reason": None},
}


def run(reviewer, key="access_reporting_after_upgrade"):
    r = reviewer.post(f"{WS}/scenarios/{key}/run")
    assert r.status_code == 200, r.text
    return r.json()


def happy_steps():
    return [tool_turn(("lookup_customer", {"mentioned_emails": []}), ("get_subscription", {})),
            tool_turn(("search_knowledge_base", {"query": "roles after a plan upgrade reporting", "top_k": 6})),
            final_turn(SIMPLE_FINAL)]


def test_live_happy_path_produces_valid_proposal_with_valid_citations(live, reviewer, db):
    fake = live.script(load_fixture("access_reporting_after_upgrade"))
    d = run(reviewer)
    assert d["state"] == "awaiting_review", d["state_reason"]
    p = d["proposal"]
    c = p["version"]["content"]
    assert p["provider"] == "Live — Claude claude-haiku-5-5"
    assert c["provider_label"] == "Live — Claude claude-haiku-5-5" and c["simulated"] is False
    assert c["next_action"] == "resolve" and "Jordan Patel" in c["draft_reply"]
    # Citations survived server validation: each cites a chunk retrieved for this request.
    assert c["citations"] and all(x["doc_slug"] == "roles-and-permissions" for x in c["citations"])
    retrieved = {e["summary"]["result"]["passages"][i]["chunk_id"]
                 for e in d["timeline"] if e["tool_name"] == "search_knowledge_base" and e["event"] == "tool.call"
                 for i in range(len(e["summary"]["result"]["passages"]))}
    assert {x["chunk_id"] for x in c["citations"]} <= retrieved
    # Account facts come from tool results, not the model.
    assert any(f["label"] == "Account" and "Brightline" in f["value"] for f in c["account_facts"])
    # The model's tool calls ran through the gate and are attributed to it in the timeline.
    model_tools = [e["tool_name"] for e in d["timeline"] if e["event"] == "tool.call" and e["actor"] == "ai:claude"]
    assert model_tools.count("search_knowledge_base") == 2 and "propose_ticket_action" in model_tools
    # Usage from the API usage fields is recorded on the proposal and the run.
    inp, out = fixture_tokens("access_reporting_after_upgrade")
    u = p["usage"]
    assert (u["provider"], u["model"], u["input_tokens"], u["output_tokens"]) == ("live", "claude-haiku-5-5", inp, out)
    assert u["tool_steps"] == 5 and u["api_calls"] == 4 and u["latency_ms"] >= 0
    runs = d["ai_runs"]
    assert len(runs) == 1 and runs[0]["provider"] == "live" and runs[0]["status"] == "succeeded"
    assert runs[0]["input_tokens"] == inp and runs[0]["tool_steps"] == 5
    # Request shape: allowlisted tools only, structured output, untrusted wrapping, no secrets in the prompt.
    first = fake.calls[0]
    assert {t["name"] for t in first["tools"]} == ALLOWLIST and all(t["strict"] for t in first["tools"])
    assert first["model"] == "claude-haiku-5-5" and first["thinking"] == {"type": "adaptive"}
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert first["max_tokens"] == live.settings.live_max_output_tokens
    assert "<customer_message>" in first["messages"][0]["content"]
    assert "untrusted" in first["system"].lower()
    assert FAKE_KEY not in json.dumps(fake.calls, default=str)
    assert FAKE_KEY not in json.dumps(d)


def test_live_escalation_rule_overrides_model(live, reviewer):
    live.script(load_fixture("connector_outage"))
    d = run(reviewer, "connector_outage")
    assert d["state"] == "awaiting_review", d["state_reason"]
    c = d["proposal"]["version"]["content"]
    assert c["next_action"] == "escalate"  # model said resolve; the rule decides
    assert c["ticket_action"]["type"] == "create_ticket"
    assert c["ticket_action"]["group"] == "Engineering — Data Connectors"
    assert "connector-outage-paid" in [h["key"] for h in c["rule_hits"]]


def test_live_processes_new_free_text_request(live, reviewer):
    live.script(happy_steps())
    cid = customer_id(reviewer, "Brightline Logistics")
    r = reviewer.post(f"{WS}/requests", json={"subject": "Exports", "body": "Can Viewers see the new Reporting tab?",
                                              "customer_id": cid})
    d = r.json()
    assert r.status_code == 200 and d["state"] == "awaiting_review", d.get("state_reason")
    assert d["proposal"]["version"]["content"]["simulated"] is False


def test_server_fills_required_context_the_model_skipped(live, reviewer):
    live.script([tool_turn(("search_knowledge_base", {"query": "reporting roles", "top_k": 4})),
                 final_turn(SIMPLE_FINAL)])
    d = run(reviewer)
    assert d["state"] == "awaiting_review", d["state_reason"]
    server_tools = [e["tool_name"] for e in d["timeline"] if e["event"] == "tool.call" and e["actor"].startswith("reviewer:")]
    assert {"lookup_customer", "get_subscription", "get_existing_tickets"} <= set(server_tools)
    labels = [f["label"] for f in d["proposal"]["version"]["content"]["account_facts"]]
    assert "Plan" in labels and "Account" in labels


def test_tool_loop_is_capped(live, reviewer):
    live.set(live_max_tool_steps=2)
    fake = live.script([tool_turn(("get_subscription", {})) for _ in range(5)])
    d = run(reviewer)
    assert d["state"] == "error" and "tool-call limit (2 steps)" in d["state_reason"]
    assert d["proposal"] is None  # no simulated fallback
    assert len(fake.calls) == 3
    assert any(e["event"] == "ai.tool_limit" for e in d["timeline"])
    assert d["ai_runs"][0]["status"] == "error" and d["ai_runs"][0]["tool_steps"] == 2


def test_retry_then_success(live, reviewer):
    fake = live.script([api_error(anthropic.RateLimitError, 429), api_error(anthropic.OverloadedError, 529),
                        *happy_steps()])
    d = run(reviewer)
    assert d["state"] == "awaiting_review", d["state_reason"]
    assert len([e for e in d["timeline"] if e["event"] == "ai.retry"]) == 2
    assert d["proposal"]["usage"]["api_calls"] == 3 and len(fake.calls) == 5


def test_timeout_is_retried(live, reviewer):
    live.script([timeout_error(), *happy_steps()])
    d = run(reviewer)
    assert d["state"] == "awaiting_review", d["state_reason"]
    assert [e["error"] for e in d["timeline"] if e["event"] == "ai.retry"] == ["timeout"]


def test_retries_exhausted_goes_to_error_without_fallback(live, reviewer):
    live.set(live_max_retries=2)
    fake = live.script([api_error(anthropic.InternalServerError, 500) for _ in range(3)])
    d = run(reviewer)
    assert d["state"] == "error" and "unavailable after 3 attempt(s)" in d["state_reason"]
    assert d["proposal"] is None and len(fake.calls) == 3
    assert not any("Simulated" in json.dumps(e["summary"]) for e in d["timeline"])
    assert any(e["event"] == "ai.call_failed" for e in d["timeline"])
    # Reprocessing is the explicit recovery path.
    assert d["allowed_actions"]["run"] is True


def test_non_retryable_error_fails_immediately(live, reviewer):
    fake = live.script([api_error(anthropic.AuthenticationError, 401), *happy_steps()])
    d = run(reviewer)
    assert d["state"] == "error" and "rejected the API key" in d["state_reason"]
    assert len(fake.calls) == 1
    fake = live.script([api_error(anthropic.BadRequestError, 400)])
    d = run(reviewer)
    assert d["state"] == "error" and "(400)" in d["state_reason"] and len(fake.calls) == 1


def test_missing_key_is_a_clear_configuration_error(live, reviewer):
    live.set(anthropic_api_key="")
    live.script([])
    d = run(reviewer)
    assert d["state"] == "error"
    assert d["state_reason"].startswith("Live mode: ANTHROPIC_API_KEY not configured")
    assert d["proposal"] is None and live.factory_calls == 0
    assert d["ai_runs"][0]["provider"] == "live" and d["ai_runs"][0]["status"] == "error"


def test_refusal_and_max_tokens_are_errors(live, reviewer):
    live.script([response([], "refusal")])
    assert "declined" in run(reviewer)["state_reason"]
    live.script([response([], "max_tokens")])
    assert "output limit" in run(reviewer)["state_reason"]


def test_output_failing_schema_is_an_error_not_a_proposal(live, reviewer):
    bad = json.loads(json.dumps(SIMPLE_FINAL))
    bad["proposal"]["approved"] = True  # extra field: forbidden by the schema
    live.script([final_turn(bad)])
    d = run(reviewer)
    assert d["state"] == "error" and "schema validation" in d["state_reason"]
    assert d["proposal"] is None and d["approvals"] == []


def test_per_request_token_cap(live, reviewer):
    live.set(live_max_tokens_per_request=2000)
    live.script(happy_steps())
    d = run(reviewer)
    assert d["state"] == "error" and "per-request token limit" in d["state_reason"]
    assert d["ai_runs"][0]["input_tokens"] > 0  # spent tokens still count toward the budget


def test_haiku_5_5_requests_send_no_refusal_fallback(live, reviewer, db):
    # Claude Haiku 5.5 has no server-side fallback, so the fallbacks parameter and its beta header must
    # never be sent to it, even though LIVE_REFUSAL_FALLBACK defaults to true.
    assert live.settings.live_model == "claude-haiku-5-5" and live.settings.live_refusal_fallback is True
    fake = live.script(load_fixture("access_reporting_after_upgrade"))
    assert run(reviewer)["state"] == "awaiting_review"
    assert all("fallbacks" not in c and "betas" not in c for c in fake.calls)


def test_fallback_still_sent_to_models_that_support_it(live, reviewer, db):
    live.set(live_model="claude-opus-5-5")
    fake = live.script(load_fixture("access_reporting_after_upgrade"))
    run(reviewer)
    first = fake.calls[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert first["betas"] == ["server-side-fallback-2026-07-01"]
