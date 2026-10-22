"""Dashboard metrics are scoped like the inbox and keep simulated and live usage apart."""
from .conftest import WS, approve_body, new_visitor, run_scenario


def test_visitor_dashboard_counts_only_own_sandbox():
    a, b = new_visitor(), new_visitor()
    d = run_scenario(a, "connector_outage")
    assert a.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).status_code == 200
    run_scenario(a, "billing_charged_twice")
    da, db_ = a.get(f"{WS}/dashboard").json(), b.get(f"{WS}/dashboard").json()
    assert da["scope"] == "Your demo sandbox only"
    assert da["requests"]["total"] == 2
    assert da["requests"]["by_category"] == {"product_issue": 1, "billing": 1}
    assert da["approval_outcomes"]["approved_as_drafted"] == 1
    assert da["executions"] == da["executions"] | {"total": 1, "succeeded": 1, "failed": 0}
    assert da["ai_runs"]["simulated"]["runs"] == 2 and da["ai_runs"]["live"]["runs"] == 0
    assert db_["requests"]["total"] == 0 and db_["executions"]["total"] == 0


def test_edit_then_approve_and_reject_are_counted_separately():
    v = new_visitor()
    d = run_scenario(v, "connector_outage")
    edited = v.put(f"{WS}/requests/{d['id']}/proposal", json={
        "base_version": 1, "draft_reply": d["proposal"]["version"]["content"]["draft_reply"] + "\n\nThanks!"}).json()
    assert v.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(edited)).status_code == 200
    r = run_scenario(v, "billing_charged_twice")
    assert v.post(f"{WS}/requests/{r['id']}/reject", json={"proposal_version_id": r["proposal"]["version"]["id"],
                                                          "reason": "test"}).status_code == 200
    o = v.get(f"{WS}/dashboard").json()["approval_outcomes"]
    assert o["edited_then_approved"] == 1 and o["approved_as_drafted"] == 0 and o["rejected"] == 1


def test_cost_only_with_pricing_configured(visitor):
    live = visitor.get(f"{WS}/dashboard").json()["ai_runs"]["live"]
    assert live["cost"] == {"usd": None, "note": "pricing not configured"}
