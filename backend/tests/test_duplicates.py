"""Repeated or concurrent approvals and retries cannot create duplicate tickets."""
import threading
import uuid

from sqlalchemy import func, select

from app import review
from app.adapters.base import ExecutionTarget
from app.adapters.internal import InternalTicketAdapter
from app.db import SessionLocal
from app.models import Approval, Execution, Ticket, Workspace
from app.schemas import ApproveIn, TicketAction

from .conftest import WS, approve_body, run_scenario


def _count(db, model, request_id):
    return db.scalar(select(func.count()).select_from(model).where(model.request_id == request_id))


def test_double_approve_creates_one_ticket(visitor, db):
    d = run_scenario(visitor, "connector_outage")
    first = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d))
    second = visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d))
    assert first.status_code == 200 and second.status_code == 409
    assert _count(db, Ticket, d["id"]) == 1
    assert _count(db, Execution, d["id"]) == 1


def test_concurrent_approvals_create_one_ticket(visitor, db):
    d = run_scenario(visitor, "connector_outage")
    body = ApproveIn(**approve_body(d))
    barrier = threading.Barrier(5)
    results: list[str] = []

    def worker():
        s = SessionLocal()
        try:
            barrier.wait()
            review.approve(s, uuid.UUID(d["id"]), "visitor:test", body)
            results.append("ok")
        except review.ReviewError:
            results.append("conflict")
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1 and results.count("conflict") == 4
    assert _count(db, Ticket, d["id"]) == 1
    assert db.scalar(select(func.count()).select_from(Approval).where(
        Approval.request_id == d["id"], Approval.status == "active")) == 1


def test_adapter_is_idempotent_by_key(db):
    ws = db.scalar(select(Workspace).where(Workspace.slug == "northstar"))
    target = ExecutionTarget(ws.id, None, None, None, "product_issue")
    action = TicketAction(type="create_ticket", subject="s", body="b", priority="normal",
                          group="Support Tier 1", status="open")
    key = uuid.uuid4().hex + uuid.uuid4().hex
    a = InternalTicketAdapter().create_ticket(db, target, action, key)
    b = InternalTicketAdapter().create_ticket(db, target, action, key)
    assert a.created and not b.created and a.ticket_id == b.ticket_id
    db.rollback()


def test_retry_after_success_is_refused(visitor, db):
    d = run_scenario(visitor, "access_reporting_after_upgrade")
    visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d))
    assert visitor.post(f"{WS}/requests/{d['id']}/retry").status_code == 409
    assert visitor.post(f"{WS}/requests/{d['id']}/run").status_code == 409
    assert _count(db, Ticket, d["id"]) == 1
