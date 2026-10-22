"""Approval versioning, pre-approval safety, bounded retries and failure handling."""
from sqlalchemy import func, select

from app.adapters.internal import FAULTS
from app.models import Approval, Execution, Ticket

from .conftest import WS, approve_body, run_scenario


def _tickets_for(db, request_id):
    return db.scalar(select(func.count()).select_from(Ticket).where(Ticket.request_id == request_id))


def test_running_workflow_creates_no_ticket(visitor, db):
    before = db.scalar(select(func.count()).select_from(Ticket))
    d = run_scenario(visitor, "connector_outage")
    assert d["proposal"]["version"]["content"]["ticket_action"]["type"] == "create_ticket"
    assert db.scalar(select(func.count()).select_from(Ticket)) == before
    assert _tickets_for(db, d["id"]) == 0
    assert visitor.post(f"{WS}/requests/{d['id']}/retry").status_code == 409


def test_templates_cannot_be_approved(visitor):
    reqs = visitor.get(f"{WS}/requests").json()["requests"]
    tmpl = next(r for r in reqs if r["is_template"])
    r = visitor.post(f"{WS}/requests/{tmpl['id']}/approve",
                     json={"proposal_version_id": tmpl["id"], "action_hash": "0" * 64})
    assert r.status_code == 409


def test_edit_invalidates_and_old_version_cannot_be_approved(visitor, db):
    d = run_scenario(visitor, "access_reporting_after_upgrade")
    v1 = approve_body(d)
    r = visitor.put(f"{WS}/requests/{d['id']}/proposal",
                    json={"base_version": 1, "draft_reply": "Edited reply.", "note": "tone"})
    assert r.status_code == 200, r.text
    d2 = r.json()
    assert d2["proposal"]["current_version"] == 2
    assert d2["proposal"]["version"]["action_hash"] != v1["action_hash"]
    old = visitor.post(f"{WS}/requests/{d['id']}/approve", json=v1)
    assert old.status_code == 409 and "outdated" in old.json()["detail"]
    # A stale edit (based on v1) is refused too.
    assert visitor.put(f"{WS}/requests/{d['id']}/proposal",
                       json={"base_version": 1, "draft_reply": "x"}).status_code == 409
    done = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d2))
    assert done.status_code == 200 and done.json()["state"] == "completed"
    assert _tickets_for(db, d["id"]) == 1


def test_action_hash_must_match(visitor):
    d = run_scenario(visitor, "connector_outage")
    body = approve_body(d) | {"action_hash": "f" * 64}
    assert visitor.post(f"{WS}/requests/{d['id']}/approve", json=body).status_code == 409


def test_invalid_ticket_destination_rejected_on_edit(visitor):
    d = run_scenario(visitor, "connector_outage")
    ta = d["proposal"]["version"]["content"]["ticket_action"] | {"group": "Attacker Inbox"}
    r = visitor.put(f"{WS}/requests/{d['id']}/proposal", json={"base_version": 1, "ticket_action": ta})
    assert r.status_code == 422


def test_reject_then_approve_fails(visitor):
    d = run_scenario(visitor, "billing_charged_twice")
    v = d["proposal"]["version"]
    r = visitor.post(f"{WS}/requests/{d['id']}/reject", json={"proposal_version_id": v["id"], "reason": "Wrong tone"})
    assert r.status_code == 200 and r.json()["state"] == "rejected"
    assert visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).status_code == 409


def test_bounded_retries_then_success(visitor, db):
    FAULTS["fail_next"] = 2  # two transient failures, third attempt succeeds
    d = run_scenario(visitor, "connector_outage")
    r = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()
    assert r["state"] == "completed" and r["executions"][0]["attempts"] == 3
    assert _tickets_for(db, d["id"]) == 1


def test_failure_recorded_then_retry_creates_exactly_one(visitor, db):
    FAULTS["fail_next"] = 10
    d = run_scenario(visitor, "connector_outage")
    r = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()
    assert r["state"] == "failed" and r["executions"][0]["attempts"] == 3
    assert "Simulated internal ticket system failure" in r["executions"][0]["last_error"]
    assert any(e["event"] == "execution.failed" for e in r["timeline"])
    assert _tickets_for(db, d["id"]) == 0
    FAULTS["fail_next"] = 0
    r = visitor.post(f"{WS}/requests/{d['id']}/retry").json()
    assert r["state"] == "completed"
    assert _tickets_for(db, d["id"]) == 1
    assert visitor.post(f"{WS}/requests/{d['id']}/retry").status_code == 409
    assert _tickets_for(db, d["id"]) == 1


def test_failure_after_write_rolls_back_then_retry_is_single(visitor, db):
    FAULTS["fail_after_write"] = 3
    d = run_scenario(visitor, "connector_outage")
    r = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()
    assert r["state"] == "failed"
    assert _tickets_for(db, d["id"]) == 0  # savepoint rolled the partial write back
    r = visitor.post(f"{WS}/requests/{d['id']}/retry").json()
    assert r["state"] == "completed" and _tickets_for(db, d["id"]) == 1


def test_edit_after_failure_requires_new_approval(visitor, db):
    FAULTS["fail_next"] = 10
    d = run_scenario(visitor, "connector_outage")
    visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d))
    FAULTS["fail_next"] = 0
    ta = d["proposal"]["version"]["content"]["ticket_action"] | {"priority": "urgent"}
    d2 = visitor.put(f"{WS}/requests/{d['id']}/proposal", json={"base_version": 1, "ticket_action": ta}).json()
    assert d2["state"] == "awaiting_review"
    approvals = db.scalars(select(Approval).where(Approval.request_id == d["id"])).all()
    assert [a.status for a in approvals] == ["invalidated"]
    assert visitor.post(f"{WS}/requests/{d['id']}/retry").status_code == 409
    assert visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).status_code == 409
    done = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d2)).json()
    assert done["state"] == "completed"
    t = db.scalar(select(Ticket).where(Ticket.request_id == d["id"]))
    assert t.priority == "urgent"
    assert db.scalar(select(func.count()).select_from(Execution).where(Execution.request_id == d["id"])) == 2


def test_audit_trail_covers_every_step(visitor):
    d = run_scenario(visitor, "connector_outage")
    r = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()
    events = [e["event"] for e in r["timeline"]]
    for ev in ("workflow.started", "ai.classify", "tool.call", "ai.synthesize", "proposal.created",
               "approval.granted", "execution.attempt", "execution.succeeded"):
        assert ev in events, ev
    tools = {e["tool_name"] for e in r["timeline"] if e["event"] == "tool.call"}
    assert tools == {"lookup_customer", "get_subscription", "get_existing_tickets", "search_knowledge_base",
                     "propose_ticket_action"}
    assert all(e["duration_ms"] is not None for e in r["timeline"] if e["event"] == "tool.call")
