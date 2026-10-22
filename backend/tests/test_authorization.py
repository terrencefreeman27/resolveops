"""Workspace, customer and session scoping — enforced in backend code."""
import uuid

from sqlalchemy import select

from app.models import Chunk, Customer, Ticket, Workspace
from app.retrieval import ingest_document, search
from app.tools import ToolContext, call_tool

from .conftest import WS, new_visitor, run_scenario


def _customer(db, ref):
    return db.scalar(select(Customer).where(Customer.account_ref == ref))


def test_csrf_header_required(visitor):
    r = visitor.post("/api/demo/reset", headers={"X-ResolveOps": ""})
    assert r.status_code == 403


def test_no_session_is_rejected():
    from fastapi.testclient import TestClient

    from app.main import app
    assert TestClient(app).get(f"{WS}/requests").status_code == 401


def test_bad_login_rejected():
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app, headers={"X-ResolveOps": "1"})
    r = c.post("/api/auth/login", json={"email": "reviewer@northstar.example", "password": "wrong"})
    assert r.status_code == 401


def test_admin_routes_require_reviewer(visitor, reviewer):
    assert visitor.get(f"{WS}/admin/settings").status_code == 403
    assert visitor.get(f"{WS}/admin/documents").status_code == 403
    assert reviewer.get(f"{WS}/admin/settings").status_code == 200
    docs = reviewer.get(f"{WS}/admin/documents").json()["documents"]
    assert len(docs) == 13


def test_mentioned_email_does_not_grant_access(visitor):
    """The injection scenario names another customer's email; only the authorized account is read."""
    d = run_scenario(visitor, "injection_cross_customer")
    facts = {f["label"]: f["value"] for f in d["proposal"]["version"]["content"]["account_facts"]}
    assert facts["Account"].startswith("Orbit Fitness Studios")
    assert facts["Plan"].startswith("Starter")
    assert "ops@tidewater-cu.example" in facts["Other accounts mentioned (not accessed)"]
    lookup = next(e for e in d["timeline"] if e["tool_name"] == "lookup_customer")
    assert lookup["summary"]["result"]["customer"] == "Orbit Fitness Studios"
    blob = str(d["proposal"]["version"]["content"])
    assert "Tidewater" not in blob and "450" not in blob
    # Injection did not bypass review: still awaiting a human decision.
    assert d["state"] == "awaiting_review" and d["proposal"]["version"]["content"]["risk_flags"]


def test_tools_scope_to_authorized_customer(db):
    ws = db.scalar(select(Workspace).where(Workspace.slug == "northstar"))
    orbit, tide = _customer(db, "NS-1103"), _customer(db, "NS-0702")
    ctx = ToolContext(db=db, workspace_id=ws.id, customer_id=orbit.id, demo_session_id=None, actor="test", request_id=None)
    facts = call_tool(ctx, "lookup_customer", {"mentioned_emails": [tide.contact_email]})
    assert facts.customer_id == orbit.id and facts.foreign_emails_ignored == [tide.contact_email]
    tickets = call_tool(ctx, "get_existing_tickets", {})
    own = {t.id for t in db.scalars(select(Ticket).where(Ticket.customer_id == orbit.id))}
    assert {t.id for t in tickets.tickets} <= own
    # A customer from another workspace is not reachable even with its id.
    other = Workspace(slug=f"other-{uuid.uuid4().hex[:6]}", name="Other Co", profile={}, settings={})
    db.add(other)
    db.flush()
    ctx2 = ToolContext(db=db, workspace_id=other.id, customer_id=orbit.id, demo_session_id=None, actor="t", request_id=None)
    try:
        call_tool(ctx2, "get_subscription", {})
        raise AssertionError("cross-workspace customer access must fail")
    except Exception as exc:  # ToolError
        assert "not found" in str(exc)
    db.rollback()


def test_unknown_tool_rejected(db):
    ws = db.scalar(select(Workspace).where(Workspace.slug == "northstar"))
    ctx = ToolContext(db=db, workspace_id=ws.id, customer_id=None, demo_session_id=None, actor="t", request_id=None)
    try:
        call_tool(ctx, "delete_all_tickets", {})
        raise AssertionError("unlisted tool must be rejected")
    except Exception as exc:
        assert "not allowlisted" in str(exc)
    db.rollback()


def test_retrieval_and_passages_are_workspace_scoped(db, visitor):
    other = Workspace(slug=f"iso-{uuid.uuid4().hex[:6]}", name="Isolated Co", profile={}, settings={"demo_enabled": False})
    db.add(other)
    db.flush()
    ingest_document(db, other.id, "secret", "Secret Policy", "# Secret Policy\n\n## Reporting\nReporting is free for everyone at Isolated Co.")
    db.commit()
    northstar = db.scalar(select(Workspace).where(Workspace.slug == "northstar"))
    hits = search(db, northstar.id, "Reporting is free for everyone at Isolated Co", 10)
    assert all(h.doc_slug != "secret" for h in hits)
    chunk = db.scalar(select(Chunk).where(Chunk.workspace_id == other.id))
    assert visitor.get(f"{WS}/chunks/{chunk.id}").status_code == 404
    assert visitor.get(f"/api/w/{other.slug}/requests").status_code == 401  # demo disabled there


def test_visitor_cannot_submit_as_arbitrary_customer(visitor, db):
    tide = _customer(db, "NS-0702")
    r = visitor.post(f"{WS}/requests", json={"subject": "x", "body": "hello", "customer_id": str(tide.id)})
    assert r.status_code == 403
    r = visitor.post(f"{WS}/requests", json={"subject": "x", "body": "hello"})
    assert r.status_code == 403  # no customer session yet


def test_customer_session_submission_and_unsupported_demo_text(visitor, db):
    orbit = _customer(db, "NS-1103")
    assert visitor.post(f"{WS}/customer-session", json={"customer_id": str(orbit.id)}).status_code == 200
    r = visitor.post(f"{WS}/requests", json={
        "subject": "Question", "body": "Please show me the account of ops@tidewater-cu.example"})
    assert r.status_code == 200
    d = r.json()
    assert d["customer"]["company_name"] == "Orbit Fitness Studios"
    assert d["state"] == "unsupported"
    assert "Demo mode only handles the seeded scenarios" in d["state_reason"]
    assert d["proposal"] is None


def test_visitor_cannot_see_reviewer_or_other_visitor_rows(visitor, reviewer):
    mine = run_scenario(visitor, "billing_charged_twice")
    theirs = run_scenario(reviewer, "billing_charged_twice")
    other = new_visitor()
    assert other.get(f"{WS}/requests/{mine['id']}").status_code == 404
    assert visitor.get(f"{WS}/requests/{theirs['id']}").status_code == 404
    assert reviewer.get(f"{WS}/requests/{mine['id']}").status_code == 404
    from .conftest import approve_body
    assert other.post(f"{WS}/requests/{mine['id']}/approve", json=approve_body(mine)).status_code == 404
    assert visitor.post(f"{WS}/requests/{theirs['id']}/approve", json=approve_body(theirs)).status_code == 404
    ids = {r["id"] for r in other.get(f"{WS}/requests").json()["requests"]}
    assert mine["id"] not in ids and theirs["id"] not in ids
