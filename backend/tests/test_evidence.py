"""Insufficient / conflicting evidence → clarify or escalate, never a confident resolve; and the second
company (Lumen Ledger) answers the same wording differently from its own documents."""
from app.providers.simulated import SimulatedProvider

from .conftest import LUMEN, WS


def _run(client, base, key):
    r = client.post(f"{base}/scenarios/{key}/run")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "awaiting_review", d["state_reason"]
    return d


def test_conflicting_documents_force_escalation(visitor):
    c = _run(visitor, LUMEN, "downgrade_timing_conflict")["proposal"]["version"]["content"]
    ec = c["evidence_check"]
    assert ec["status"] == "conflicting" and c["next_action"] == "escalate"
    conflict = ec["conflicts"][0]
    assert conflict["key"] == "plan_change.downgrade_effective"
    assert {v["doc_title"] for v in conflict["values"]} == {"Changing Plans", "Billing FAQ"}
    assert "resolve" in ec["effect"] and "Billing FAQ" in c["escalation_reason"]
    assert c["ticket_action"]["type"] == "create_ticket" and c["ticket_action"]["group"] == "Billing Operations"
    assert "end of your current annual term" not in c["draft_reply"]  # the confident draft was withheld


def test_insufficient_evidence_forces_escalation(visitor):
    c = _run(visitor, LUMEN, "peppol_einvoicing")["proposal"]["version"]["content"]
    ec = c["evidence_check"]
    assert ec["status"] == "insufficient" and ec["best_score"] < ec["threshold"]
    assert c["next_action"] == "escalate" and "relevance threshold" in c["escalation_reason"]
    assert not c["draft_reply"].startswith("Hi Felipe,\n\nYes")


def test_evidence_guard_overrides_a_forced_resolve(visitor, monkeypatch):
    """Even if the provider drafts 'resolve', unsupported evidence can't yield a resolve."""
    orig = SimulatedProvider.synthesize
    monkeypatch.setattr(SimulatedProvider, "synthesize",
                        lambda self, inp: orig(self, inp).model_copy(update={"next_action": "resolve"}))
    for key in ("downgrade_timing_conflict", "peppol_einvoicing"):
        assert _run(visitor, LUMEN, key)["proposal"]["version"]["content"]["next_action"] == "escalate"


def test_reviewer_edit_cannot_turn_unsupported_evidence_into_resolve(visitor):
    d = _run(visitor, LUMEN, "downgrade_timing_conflict")
    r = visitor.put(f"{LUMEN}/requests/{d['id']}/proposal", json={"base_version": 1, "next_action": "resolve"})
    assert r.status_code == 422 and "conflicting" in r.json()["detail"]
    ok = visitor.put(f"{LUMEN}/requests/{d['id']}/proposal", json={"base_version": 1, "next_action": "clarify"})
    assert ok.status_code == 200


def test_sufficient_evidence_is_recorded(visitor):
    c = _run(visitor, WS, "access_reporting_after_upgrade")["proposal"]["version"]["content"]
    assert c["evidence_check"]["status"] == "sufficient" and c["evidence_check"]["effect"] is None


def test_same_access_wording_different_company_different_answer(visitor):
    ns = _run(visitor, WS, "access_reporting_after_upgrade")
    ll = _run(visitor, LUMEN, "access_reporting_after_upgrade")
    assert ns["body"] == ll["body"]  # identical customer wording
    a, b = ns["proposal"]["version"]["content"], ll["proposal"]["version"]["content"]
    a_docs = {c["document_id"] for c in a["citations"]}
    b_docs = {c["document_id"] for c in b["citations"]}
    assert a_docs and b_docs and not (a_docs & b_docs)
    assert {c["doc_slug"] for c in b["citations"]} >= {"plans-and-pricing", "team-roles"}
    # Key fact differs: Northstar says change the users' role to Analyst (Pro includes Reporting);
    # Lumen says Growth doesn't include reporting at all — Scale is required.
    assert "Analyst" in a["draft_reply"] and "Scale" not in a["draft_reply"]
    assert "only included on the Scale plan" in b["draft_reply"] and "Analyst" not in b["draft_reply"]
    assert a["draft_reply"].endswith("Northstar Support") and b["draft_reply"].endswith("Lumen Ledger Customer Care")


def test_same_billing_wording_different_company_different_answer(visitor):
    ns = _run(visitor, WS, "billing_charged_twice")
    ll = _run(visitor, LUMEN, "billing_charged_twice")
    assert ns["body"] == ll["body"]
    a, b = ns["proposal"]["version"]["content"], ll["proposal"]["version"]["content"]
    assert not ({c["document_id"] for c in a["citations"]} & {c["document_id"] for c in b["citations"]})
    assert a["next_action"] == "clarify" and "prorated" in a["draft_reply"]
    assert b["next_action"] == "resolve" and "doesn't prorate" in b["draft_reply"] and "account credit" in b["draft_reply"]


def test_same_refund_wording_routes_by_each_companys_rules(visitor):
    a = _run(visitor, WS, "refund_unused_seats")["proposal"]["version"]["content"]
    b = _run(visitor, LUMEN, "refund_unused_seats")["proposal"]["version"]["content"]
    assert (a["ticket_action"]["group"], a["ticket_action"]["priority"]) == ("Billing", "normal")
    assert (b["ticket_action"]["group"], b["ticket_action"]["priority"]) == ("Accounts Receivable", "high")
