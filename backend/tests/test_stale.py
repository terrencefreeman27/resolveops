"""Stale-evidence invalidation (SPEC §9): replacing/deleting documents and changing escalation rules
stale pending proposals in the same transaction; approve/retry are refused; Reprocess adds a new version."""
from pathlib import Path

import pytest
from sqlalchemy import select

from app import documents
from app.adapters.internal import FAULTS
from app.db import SessionLocal
from app.models import (Approval, Document, DocumentVersion, Proposal, ProposalEvidence, ProposalVersion,
                        SupportRequest, Workspace)

from .conftest import WS, approve_body, new_workspace, run_scenario, upload

ROLES = Path(__file__).parents[1] / "app/seed/docs/northstar/roles-and-permissions.md"


def _doc(db, slug="roles-and-permissions"):
    ws = db.scalar(select(Workspace).where(Workspace.slug == "northstar"))
    return db.scalar(select(Document).where(Document.workspace_id == ws.id, Document.slug == slug))


@pytest.fixture
def restore_roles(reviewer):
    yield
    with SessionLocal() as s:
        d = _doc(s)
        cur = s.get(DocumentVersion, d.current_version_id)
        if cur.content != ROLES.read_text():
            assert upload(reviewer, "northstar", "roles-and-permissions.md", ROLES.read_text(), str(d.id)).status_code == 202


def _replace_roles(reviewer, db, extra="\nRole changes are logged in the audit trail.\n"):
    d = _doc(db)
    r = upload(reviewer, "northstar", "roles-and-permissions.md", ROLES.read_text() + extra, str(d.id))
    assert r.status_code == 202, r.text
    db.expire_all()


def test_replacement_marks_pending_stale_in_same_transaction(reviewer, db, restore_roles):
    d = run_scenario(reviewer, "access_reporting_after_upgrade")
    doc = _doc(db)
    old_version_id = doc.current_version_id
    with SessionLocal() as s1, SessionLocal() as s2:
        v = documents.create_replacement(s1, s1.get(Document, doc.id), "roles.md", ROLES.read_text() + "\nX.\n", "test")
        documents.index_version(s1, v, "test")
        # Inside the transaction: old version superseded AND the proposal stale, together.
        assert s1.get(DocumentVersion, old_version_id).status == "superseded"
        assert s1.get(SupportRequest, d["id"]).state == "stale"
        # Not visible to anyone else until commit.
        assert s2.get(SupportRequest, d["id"]).state == "awaiting_review"
        s1.commit()
        s2.expire_all()
        assert s2.get(SupportRequest, d["id"]).state == "stale"
        assert s2.get(DocumentVersion, old_version_id).status == "superseded"


def test_stale_cannot_be_approved_and_reprocess_creates_new_version(reviewer, db, restore_roles):
    d = run_scenario(reviewer, "access_reporting_after_upgrade")
    v1 = approve_body(d)
    cited_v1 = d["proposal"]["version"]["content"]["citations"]
    _replace_roles(reviewer, db)
    s = reviewer.get(f"{WS}/requests/{d['id']}").json()
    assert s["state"] == "stale" and s["proposal"]["status"] == "stale"
    assert "Roles and Permissions' v" in s["proposal"]["stale_reason"] and "superseded" in s["proposal"]["stale_reason"]
    assert s["allowed_actions"]["approve"] is False and s["allowed_actions"]["run"] is True
    r = reviewer.post(f"{WS}/requests/{d['id']}/approve", json=v1)
    assert r.status_code == 409 and "stale" in r.json()["detail"]
    assert reviewer.put(f"{WS}/requests/{d['id']}/proposal", json={"base_version": 1, "draft_reply": "x"}).status_code == 409
    # The old citation still opens the exact version it cited, marked as superseded.
    old = next(c for c in cited_v1 if c["doc_slug"] == "roles-and-permissions")
    p = reviewer.get(f"{WS}/chunks/{old['chunk_id']}").json()
    assert p["version"] == old["version"] and p["version_status"] == "superseded" and not p["active"]
    assert p["current_version"] > old["version"]
    # Reprocess: same proposal, next version, evidence from the current document version.
    r = reviewer.post(f"{WS}/requests/{d['id']}/run").json()
    assert r["state"] == "awaiting_review" and r["proposal"]["id"] == d["proposal"]["id"]
    assert r["proposal"]["current_version"] == 2 and "stale" in r["proposal"]["version"]["edit_note"]
    new_roles = [c for c in r["proposal"]["version"]["content"]["citations"] if c["doc_slug"] == "roles-and-permissions"]
    assert new_roles and all(c["version"] == p["current_version"] for c in new_roles)
    events = [e["event"] for e in r["timeline"]]
    assert "proposal.stale" in events and "proposal.reprocessed" in events
    done = reviewer.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(r)).json()
    assert done["state"] == "completed"


def test_failed_execution_goes_stale_and_retry_is_refused(visitor, reviewer, db, restore_roles):
    FAULTS["fail_next"] = 10
    d = run_scenario(visitor, "access_reporting_after_upgrade")
    assert visitor.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).json()["state"] == "failed"
    FAULTS["fail_next"] = 0
    _replace_roles(reviewer, db, "\nAnother clarification.\n")
    r = visitor.post(f"{WS}/requests/{d['id']}/retry")
    assert r.status_code == 409 and "stale" in r.json()["detail"]
    approvals = db.scalars(select(Approval).where(Approval.request_id == d["id"])).all()
    assert [a.status for a in approvals] == ["invalidated"] and "Evidence changed" in approvals[0].invalidated_reason
    assert visitor.get(f"{WS}/requests/{d['id']}").json()["tickets"] == []


def test_rule_change_marks_affected_pending_proposals_stale(reviewer):
    d = run_scenario(reviewer, "connector_outage")
    other = run_scenario(reviewer, "billing_charged_twice")
    rule = reviewer.post(f"{WS}/admin/rules", json={
        "name": "Snowflake outages to Billing (test)", "keywords_any": ["snowflake"], "categories": ["product_issue"],
        "action": "escalate", "group": "Billing", "priority": "urgent"})
    assert rule.status_code == 200 and rule.json()["proposals_marked_stale"] >= 1
    s = reviewer.get(f"{WS}/requests/{d['id']}").json()
    assert s["state"] == "stale" and "Escalation rules changed" in s["proposal"]["stale_reason"]
    assert reviewer.get(f"{WS}/requests/{other['id']}").json()["state"] == "awaiting_review"  # unaffected
    r = reviewer.post(f"{WS}/requests/{d['id']}/run").json()
    assert r["proposal"]["version"]["content"]["ticket_action"]["group"] == "Billing"
    gone = reviewer.delete(f"{WS}/admin/rules/{rule.json()['id']}")
    assert gone.status_code == 200, gone.text
    assert reviewer.get(f"{WS}/requests/{d['id']}").json()["state"] == "stale"  # rule removed again


def test_deleting_a_document_stales_proposals_that_used_it(reviewer, db):
    slug = new_workspace(reviewer)
    doc = upload(reviewer, slug, "refunds.md", "# Refunds\n\n## Window\nRefunds within 30 days.").json()
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
    dv = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc["id"]))
    from app.models import Chunk
    chunk = db.scalar(select(Chunk).where(Chunk.document_version_id == dv.id))
    req = SupportRequest(workspace_id=ws.id, submitted_via="reviewer", from_name="A", from_email="a@x.example",
                         subject="Refund", body="Refund?", state="awaiting_review")
    db.add(req)
    db.flush()
    prop = Proposal(workspace_id=ws.id, request_id=req.id, provider="test", status="open")
    db.add(prop)
    db.flush()
    pv = ProposalVersion(workspace_id=ws.id, proposal_id=prop.id, version=1, content={"rule_hits": []},
                         action_hash="0" * 64, author="test")
    db.add(pv)
    db.flush()
    db.add(ProposalEvidence(workspace_id=ws.id, proposal_version_id=pv.id, document_version_id=dv.id,
                            chunk_id=chunk.id, cited=True, score=0.9))
    db.commit()
    r = reviewer.delete(f"/api/w/{slug}/admin/documents/{doc['id']}").json()
    assert r["proposals_marked_stale"] == 1
    db.expire_all()
    assert db.get(SupportRequest, req.id).state == "stale"
    assert "was deleted" in db.get(Proposal, prop.id).stale_reason
