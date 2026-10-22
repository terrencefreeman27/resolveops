"""Visitor demo sessions are isolated and reset only themselves."""
from sqlalchemy import func, select

from app.models import Ticket

from .conftest import WS, approve_body, new_visitor, run_scenario


def test_reset_only_affects_own_session(db):
    a, b = new_visitor(), new_visitor()
    da = run_scenario(a, "connector_outage")
    db_ = run_scenario(b, "connector_outage")
    a.post(f"{WS}/requests/{da['id']}/approve", json=approve_body(da))
    b.post(f"{WS}/requests/{db_['id']}/approve", json=approve_body(db_))
    seed_tickets = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.source == "seed"))

    a_ids = {r["id"] for r in a.get(f"{WS}/requests").json()["requests"]}
    b_ids = {r["id"] for r in b.get(f"{WS}/requests").json()["requests"]}
    assert da["id"] in a_ids and da["id"] not in b_ids and db_["id"] in b_ids and db_["id"] not in a_ids
    a_tickets = {t["id"] for t in a.get(f"{WS}/tickets").json()["tickets"] if t["sandbox"]}
    b_tickets = {t["id"] for t in b.get(f"{WS}/tickets").json()["tickets"] if t["sandbox"]}
    assert len(a_tickets) == 1 and len(b_tickets) == 1 and not (a_tickets & b_tickets)

    r = a.post("/api/demo/reset")
    assert r.status_code == 200 and r.json()["deleted"]["support_requests"] >= 1
    assert a.get(f"{WS}/requests/{da['id']}").status_code == 404
    assert not [t for t in a.get(f"{WS}/tickets").json()["tickets"] if t["sandbox"]]
    # B untouched, seed data untouched, templates still there for A.
    assert b.get(f"{WS}/requests/{db_['id']}").json()["state"] == "completed"
    assert {t["id"] for t in b.get(f"{WS}/tickets").json()["tickets"] if t["sandbox"]} == b_tickets
    assert db.scalar(select(func.count()).select_from(Ticket).where(Ticket.source == "seed")) == seed_tickets
    assert len([r for r in a.get(f"{WS}/requests").json()["requests"] if r["is_template"]]) == 6


def test_visitor_note_on_shared_ticket_uses_sandbox_copy(visitor, db):
    d = run_scenario(visitor, "sso_enforce")
    ta = d["proposal"]["version"]["content"]["ticket_action"]
    assert ta["type"] == "add_note"
    shared = db.get(Ticket, ta["ticket_id"])
    notes_before = list(shared.notes)
    r = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()
    assert r["state"] == "completed"
    db.expire_all()
    assert db.get(Ticket, ta["ticket_id"]).notes == notes_before
    assert r["tickets"] and r["tickets"][0]["sandbox"] and r["tickets"][0]["notes"]
