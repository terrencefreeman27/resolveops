"""Workspace isolation and reviewer-only onboarding (SPEC §2, §7, §11)."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Chunk, Customer, SupportRequest, Workspace
from app.retrieval import search
from app.schemas import CitationRef, Passage, ProposalDraft, TicketAction
from app.workflow import validate_citations

from .conftest import HDR, LUMEN, WS, approve_body, lumen_reviewer, new_visitor, new_workspace, run_scenario, upload

ONBOARDING_GETS = ["admin/settings", "admin/documents", "admin/rules", "admin/adapters"]


def _ws(db, slug):
    return db.scalar(select(Workspace).where(Workspace.slug == slug))


def test_visitors_cannot_reach_onboarding(visitor):
    for path in ONBOARDING_GETS:
        assert visitor.get(f"{WS}/{path}").status_code == 403, path
    assert visitor.post("/api/workspaces", json={"name": "Visitor Co"}).status_code == 403
    assert visitor.post(f"{WS}/admin/documents", json={"filename": "x.md", "content": "# x\n\n## y\nz"}).status_code == 403
    assert visitor.post(f"{WS}/admin/rules", json={"name": "x", "keywords_any": ["x"], "group": "Billing"}).status_code == 403
    assert visitor.put(f"{WS}/admin/adapter", json={"adapter": "internal"}).status_code == 403
    assert visitor.post(f"{WS}/admin/test-request", json={"text": "refund please"}).status_code == 403
    anon = TestClient(app, headers=HDR)
    assert anon.post("/api/workspaces", json={"name": "Anon Co"}).status_code == 403


def test_reviewer_of_lumen_cannot_read_import_or_approve_in_northstar(reviewer):
    lumen = lumen_reviewer()
    assert lumen.get(f"{LUMEN}/admin/documents").status_code == 200
    for path in ONBOARDING_GETS:
        assert lumen.get(f"{WS}/{path}").status_code in (401, 403), path
    assert lumen.post(f"{WS}/admin/documents", json={"filename": "x.md", "content": "# x\n\n## y\nz"}).status_code in (401, 403)
    assert lumen.get(f"{WS}/requests").status_code == 401  # no membership, no demo session
    d = run_scenario(reviewer, "connector_outage")  # Northstar workspace-scope request
    assert lumen.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).status_code == 401
    # Even with a visitor demo session, the Lumen reviewer is only a sandboxed visitor in Northstar.
    lumen.post("/api/demo/session")
    assert lumen.get(f"{WS}/requests/{d['id']}").status_code == 404
    assert lumen.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d)).status_code == 404
    assert lumen.get(f"{WS}/admin/documents").status_code == 403
    # The Lumen reviewer's request ids are not reachable through the Northstar path either.
    own = lumen.post(f"{LUMEN}/scenarios/billing_charged_twice/run").json()
    assert reviewer.get(f"{WS}/requests/{own['id']}").status_code == 404


def test_created_workspace_is_private_to_its_members(reviewer):
    slug = new_workspace(reviewer)
    lumen = lumen_reviewer()
    lumen.post("/api/demo/session")
    assert lumen.get(f"/api/w/{slug}/admin/documents").status_code == 401  # not demo-enabled, not a member
    assert slug not in {w["slug"] for w in lumen.get("/api/meta").json()["workspaces"]}
    assert slug not in {w["slug"] for w in new_visitor().get("/api/meta").json()["workspaces"]}
    mine = {w["slug"]: w for w in reviewer.get("/api/meta").json()["workspaces"]}
    assert mine[slug]["is_member"] and {"northstar", "lumen"} <= set(mine)


def test_retrieval_never_crosses_workspaces(db):
    ns, ll = _ws(db, "northstar"), _ws(db, "lumen")
    for ws, query in ((ll, "Snowflake connector NS-CONN-504 KI-2031"), (ns, "Insights reporting Scale plan Lumen")):
        hits = search(db, ws.id, query, 10)
        chunks = db.scalars(select(Chunk).where(Chunk.id.in_([h.chunk_id for h in hits]))).all()
        assert hits and all(c.workspace_id == ws.id for c in chunks)
    db.rollback()


def test_citation_from_another_workspace_is_rejected(visitor, db):
    ns_chunk = db.scalar(select(Chunk).where(Chunk.workspace_id == _ws(db, "northstar").id, Chunk.active.is_(True)).limit(1))
    assert visitor.get(f"{LUMEN}/chunks/{ns_chunk.id}").status_code == 404
    assert visitor.get(f"{WS}/chunks/{ns_chunk.id}").status_code == 200
    # Validation: a Lumen request cannot keep a citation to a Northstar chunk, even if a provider claims it.
    req = db.scalar(select(SupportRequest).where(SupportRequest.workspace_id == _ws(db, "lumen").id).limit(1))
    ll_chunk = db.scalar(select(Chunk).where(Chunk.workspace_id == req.workspace_id, Chunk.active.is_(True)).limit(1))
    p = Passage(chunk_id=ll_chunk.id, document_id=ll_chunk.document_id, document_version_id=ll_chunk.document_version_id,
                version=1, doc_slug="x", doc_title="X", section=ll_chunk.section, text=ll_chunk.text, score=0.9)
    draft = ProposalDraft(next_action="resolve", draft_reply="r", ticket_action=TicketAction(type="none"),
                          citations=[CitationRef(chunk_id=ns_chunk.id, claim="foreign"), CitationRef(chunk_id=ll_chunk.id, claim="ok")])
    assert [c.chunk_id for c in validate_citations(db, req, draft, [p], "test")] == [ll_chunk.id]
    db.rollback()


def test_customer_ids_do_not_cross_workspaces(reviewer, db):
    ns_customer = db.scalar(select(Customer).where(Customer.workspace_id == _ws(db, "northstar").id).limit(1))
    r = reviewer.post(f"{LUMEN}/requests", json={"subject": "x", "body": "y", "customer_id": str(ns_customer.id)})
    assert r.status_code == 403
    assert reviewer.post(f"{LUMEN}/customer-session", json={"customer_id": str(ns_customer.id)}).status_code == 404


def test_visitor_sandboxes_are_per_workspace_and_reset_only_the_caller():
    a, b = new_visitor(), new_visitor()
    a_ns = run_scenario(a, "access_reporting_after_upgrade")
    a_ll = a.post(f"{LUMEN}/scenarios/access_reporting_after_upgrade/run").json()
    b_ll = b.post(f"{LUMEN}/scenarios/access_reporting_after_upgrade/run").json()
    # A's Northstar request is not addressable through Lumen, and B sees none of A's rows.
    assert a.get(f"{LUMEN}/requests/{a_ns['id']}").status_code == 404
    for path, rid in ((WS, a_ns["id"]), (LUMEN, a_ll["id"])):
        assert b.get(f"{path}/requests/{rid}").status_code == 404
    assert a.post("/api/demo/reset").status_code == 200
    for path, rid in ((WS, a_ns["id"]), (LUMEN, a_ll["id"])):
        assert a.get(f"{path}/requests/{rid}").status_code == 404
    assert b.get(f"{LUMEN}/requests/{b_ll['id']}").json()["state"] == "awaiting_review"


def test_onboarding_flow_end_to_end(reviewer):
    slug = new_workspace(reviewer, f"Acme Widgets {uuid.uuid4().hex[:4]}")
    base = f"/api/w/{slug}"
    s = reviewer.get(f"{base}/admin/settings").json()
    assert s["settings"]["ticket_adapter"] == "internal" and s["settings"]["demo_enabled"] is False
    up = reviewer.put(f"{base}/admin/company", json={"name": "Acme Widgets", "tagline": "Widgets for teams",
                                                    "support_signature": "Acme Care", "ticket_groups": ["Support", "Billing"]})
    assert up.status_code == 200 and up.json()["profile"]["support_signature"] == "Acme Care"
    doc = upload(reviewer, slug, "refund-policy.md",
                 "# Refund Policy\n\n## Refund window\nRefunds are available within 30 days of purchase.\n\n"
                 "## Who decides\nThe Billing team approves every refund.\n").json()
    detail = reviewer.get(f"{base}/admin/documents/{doc['id']}").json()
    assert detail["version"]["import_status"] == "ready" and len(detail["sections"]) == 2
    bad_group = reviewer.post(f"{base}/admin/rules", json={"name": "Refunds", "keywords_any": ["refund"],
                                                          "group": "Nowhere"})
    assert bad_group.status_code == 422
    rule = reviewer.post(f"{base}/admin/rules", json={"name": "Refunds to Billing", "keywords_any": ["refund"],
                                                     "group": "Billing", "priority": "high"})
    assert rule.status_code == 200, rule.text
    ad = reviewer.get(f"{base}/admin/adapters").json()
    assert {a["name"]: a["available"] for a in ad["adapters"]} == {"internal": True, "github": False}
    assert reviewer.put(f"{base}/admin/adapter", json={"adapter": "github"}).status_code == 409
    assert reviewer.put(f"{base}/admin/adapter", json={"adapter": "internal"}).json()["selected"] == "internal"
    t = reviewer.post(f"{base}/admin/test-request", json={"text": "Can I get a refund for last week's order?",
                                                         "category": "billing"}).json()
    assert t["evidence_check"]["status"] == "sufficient" and t["passages"][0]["doc_title"] == "Refund Policy"
    assert [h["key"] for h in t["rule_hits"]] == ["refunds-to-billing"] and "Billing" in t["allowed_outcome"]
    t2 = reviewer.post(f"{base}/admin/test-request", json={"text": "Do you support Kubernetes autoscaling?"}).json()
    assert t2["evidence_check"]["status"] == "insufficient" and "clarify or escalate" in t2["allowed_outcome"]
