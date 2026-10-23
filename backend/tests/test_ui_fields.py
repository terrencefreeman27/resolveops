"""Additive, read-only fields the UI needs: inbox message preview, next action per row, planned adapter."""
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Workspace

from .conftest import WS, new_visitor, run_scenario


def _set_ws_adapter(name: str) -> None:
    with SessionLocal() as s:
        ws = s.scalar(select(Workspace).where(Workspace.slug == "northstar"))
        ws.settings = {**ws.settings, "ticket_adapter": name}
        s.commit()


def test_list_rows_carry_the_customer_message_preview(visitor):
    rows = visitor.get(f"{WS}/requests").json()["requests"]
    assert rows and all(r["is_template"] for r in rows)
    for r in rows:
        body = visitor.get(f"{WS}/requests/{r['id']}").json()["body"]
        flat = " ".join(body.split())
        assert r["preview"] == flat or (r["preview"].endswith("…") and flat.startswith(r["preview"][:-1]))
        assert len(r["preview"]) <= 180
        assert r["next_action"] is None  # templates are never processed


def test_list_next_action_follows_the_current_proposal_and_stays_scoped(visitor):
    d = run_scenario(visitor, "billing_charged_twice")
    rows = {r["id"]: r for r in visitor.get(f"{WS}/requests").json()["requests"]}
    assert rows[d["id"]]["next_action"] == "clarify" == d["next_action"]
    assert rows[d["id"]]["preview"].startswith(" ".join(d["body"].split())[:40])
    other = new_visitor()
    assert d["id"] not in {r["id"] for r in other.get(f"{WS}/requests").json()["requests"]}
    # Editing the next action is reflected (current version, not the first one).
    edited = visitor.put(f"{WS}/requests/{d['id']}/proposal",
                         json={"base_version": 1, "next_action": "escalate"}).json()
    assert edited["next_action"] == "escalate"
    rows = {r["id"]: r for r in visitor.get(f"{WS}/requests").json()["requests"]}
    assert rows[d["id"]]["next_action"] == "escalate"


def test_planned_adapter_matches_the_executor_rule(visitor, reviewer):
    billing = run_scenario(visitor, "billing_charged_twice")
    assert billing["proposal"]["version"]["content"]["ticket_action"]["type"] == "none"
    assert billing["proposal"]["planned_adapter"] is None
    outage = run_scenario(visitor, "connector_outage")
    assert outage["proposal"]["version"]["content"]["ticket_action"]["type"] == "create_ticket"
    assert outage["proposal"]["planned_adapter"] == "internal"
    _set_ws_adapter("github")
    try:
        # Visitor sandboxes never reach external integrations, even when the workspace selects GitHub.
        assert visitor.get(f"{WS}/requests/{outage['id']}").json()["proposal"]["planned_adapter"] == "internal"
        r = run_scenario(reviewer, "connector_outage")
        assert r["proposal"]["planned_adapter"] == "github"
        access = run_scenario(reviewer, "access_reporting_after_upgrade")
        if access["proposal"]["version"]["content"]["ticket_action"]["type"] != "none":
            assert access["proposal"]["planned_adapter"] == "internal"  # non-escalation tickets stay internal
    finally:
        _set_ws_adapter("internal")
