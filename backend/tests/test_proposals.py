"""Citation validation, evidence provenance, fact-driven answers, document versions in retrieval."""
import uuid

from sqlalchemy import select

from app.models import Chunk, ProposalEvidence, SimFixture, SupportRequest, Workspace
from app.providers.simulated import SimulatedProvider, normalize
from app.retrieval import ingest_document, search
from app.schemas import CitationRef, Passage, ProposalDraft, TicketAction
from app.seed import northstar as N
from app.workflow import validate_citations

from .conftest import WS, run_scenario


def test_every_seeded_request_has_a_workspace_fixture(db):
    """Simulated fixtures are workspace-scoped rows, one per seeded scenario of that workspace."""
    from app.seed import lumen as L
    for mod in (N, L):
        ws = db.scalar(select(Workspace).where(Workspace.slug == mod.WORKSPACE["slug"]))
        fixtures = {f.match_text: f.key for f in db.scalars(select(SimFixture).where(SimFixture.workspace_id == ws.id))}
        for key, _ref, _subj, body, _ago in mod.REQUESTS:
            assert fixtures.get(normalize(body)) == key


def test_citations_must_be_retrieved_for_this_request(db):
    req = db.scalar(select(SupportRequest).where(SupportRequest.is_template.is_(True)).limit(1))
    chunk = db.scalar(select(Chunk).where(Chunk.workspace_id == req.workspace_id, Chunk.active.is_(True)).limit(1))
    p = Passage(chunk_id=chunk.id, document_id=chunk.document_id, document_version_id=chunk.document_version_id,
                version=1, doc_slug="x", doc_title="X", section=chunk.section, text=chunk.text, score=0.9)
    draft = ProposalDraft(next_action="resolve", draft_reply="r", ticket_action=TicketAction(type="none"),
                          citations=[CitationRef(chunk_id=chunk.id, claim="ok"),
                                     CitationRef(chunk_id=uuid.uuid4(), claim="fabricated")])
    kept = validate_citations(db, req, draft, [p], "test")
    assert [c.chunk_id for c in kept] == [chunk.id]
    db.rollback()


def test_proposal_citations_subset_of_recorded_evidence(visitor, db):
    d = run_scenario(visitor, "connector_outage")
    v = d["proposal"]["version"]
    ev = db.scalars(select(ProposalEvidence).where(ProposalEvidence.proposal_version_id == v["id"])).all()
    retrieved = {str(e.chunk_id) for e in ev}
    cited = {str(e.chunk_id) for e in ev if e.cited}
    assert cited == {c["chunk_id"] for c in v["content"]["citations"]}
    assert cited and cited <= retrieved
    # Citation opens the passage, with its document version.
    c = v["content"]["citations"][0]
    p = visitor.get(f"{WS}/chunks/{c['chunk_id']}").json()
    assert p["version"] == c["version"] and p["active"] and p["text"]


def test_account_facts_drive_the_access_answer(visitor):
    d = run_scenario(visitor, "access_reporting_after_upgrade")
    content = d["proposal"]["version"]["content"]
    reply = content["draft_reply"]
    assert "Viewer" in reply and "Analyst" in reply and "Settings → Users & Roles" in reply
    assert "Jordan Patel" in reply and "Maya Chen" in reply  # from lookup_customer, not invented
    assert "cache" not in reply.lower()
    facts = {f["label"]: f for f in content["account_facts"]}
    assert facts["Plan change"]["value"].startswith("Starter → Pro, 1 day")
    assert facts["Plan change"]["source"] == "get_subscription"
    slugs = {c["doc_slug"] for c in content["citations"]}
    assert {"roles-and-permissions", "reporting-troubleshooting"} <= slugs
    assert content["simulated"] and content["provider_label"] == "Simulated AI — demo mode"


def test_billing_scenario_asks_for_clarification_with_real_invoices(visitor):
    content = run_scenario(visitor, "billing_charged_twice")["proposal"]["version"]["content"]
    assert content["next_action"] == "clarify" and content["missing_info"]
    assert "$1,200.00" in content["draft_reply"] and "$205.33" in content["draft_reply"]
    assert content["ticket_action"]["type"] == "none"


def test_rules_force_escalation(visitor):
    content = run_scenario(visitor, "refund_unused_seats")["proposal"]["version"]["content"]
    assert content["next_action"] == "escalate"
    assert content["ticket_action"]["group"] == "Billing"
    assert "refund-human-only" in {h["key"] for h in content["rule_hits"]}
    assert "will be refunded" not in content["draft_reply"].lower()  # never promises a refund


def test_no_evidence_means_no_resolve(visitor, monkeypatch):
    """If the provider cites nothing that was retrieved, the server will not let it 'resolve'."""
    orig = SimulatedProvider.synthesize

    def no_citations(self, inp):
        draft = orig(self, inp)
        return draft.model_copy(update={"citations": [], "next_action": "resolve"})

    monkeypatch.setattr(SimulatedProvider, "synthesize", no_citations)
    content = run_scenario(visitor, "sso_enforce")["proposal"]["version"]["content"]
    assert content["next_action"] == "escalate"
    assert "No supporting documentation" in content["escalation_reason"]


def test_superseded_versions_leave_retrieval(db):
    ws = Workspace(slug=f"life-{uuid.uuid4().hex[:6]}", name="Lifecycle Co", profile={}, settings={})
    db.add(ws)
    db.flush()
    ingest_document(db, ws.id, "refunds", "Refunds", "# Refunds\n\n## Window\nRefunds are allowed within 90 days.")
    v2 = ingest_document(db, ws.id, "refunds", "Refunds", "# Refunds\n\n## Window\nRefunds are allowed within 14 days.")
    db.flush()
    hits = search(db, ws.id, "refund window days", 5)
    assert hits and all(h.document_version_id == v2.id for h in hits)
    assert all("14 days" in h.text for h in hits)
    db.rollback()
