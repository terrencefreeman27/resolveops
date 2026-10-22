"""GitHub Issues adapter against a fake HTTP transport (no network, no real token)."""
import json
import logging
import threading

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.adapters import github
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Execution, Ticket, Workspace

from .conftest import WS, approve_body, new_reviewer, run_scenario
from .github_fakes import FAKE_TOKEN, REPO, FakeGitHub


def _set_ws_adapter(name: str) -> None:
    with SessionLocal() as s:
        ws = s.scalar(select(Workspace).where(Workspace.slug == "northstar"))
        ws.settings = {**ws.settings, "ticket_adapter": name}
        s.commit()


class GH:
    def __init__(self, monkeypatch):
        self.fake = FakeGitHub()
        self.sleeps: list[float] = []
        self.settings = get_settings()
        self.mp = monkeypatch
        self.set(github_adapter_enabled=True, github_token=SecretStr(FAKE_TOKEN), github_issues_repo=REPO,
                 github_allowed_repos=f"{REPO}, other/repo", github_labels="resolveops,synthetic-test",
                 github_retry_base_delay_s=0.5, github_max_wait_s=10.0)
        monkeypatch.setattr(github, "TRANSPORT", self.fake.transport())
        monkeypatch.setattr(github, "SLEEP", self.sleeps.append)

    def set(self, **kw):
        for k, v in kw.items():
            self.mp.setattr(self.settings, k, v)


@pytest.fixture
def gh(monkeypatch):
    harness = GH(monkeypatch)
    _set_ws_adapter("github")
    yield harness
    _set_ws_adapter("internal")


def _escalation(client):
    d = run_scenario(client, "connector_outage")
    assert d["proposal"]["version"]["content"]["next_action"] == "escalate"
    return d


def _approve(client, d):
    return client.post(f"{WS}/requests/{d['id']}/approve", json=approve_body(d))


def _ex(db, request_id) -> Execution:
    db.expire_all()
    return db.scalar(select(Execution).where(Execution.request_id == request_id))


def test_success_creates_issue_and_stores_number_id_url(gh, reviewer, db):
    d = _escalation(reviewer)
    r = _approve(reviewer, d)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["state"] == "completed"
    assert gh.fake.creates == 1 and len(gh.fake.issues) == 1
    issue = gh.fake.issues[0]
    ex = out["executions"][-1]
    assert ex["adapter"] == "github" and ex["external_number"] == 1
    assert ex["external_url"] == f"https://github.com/{REPO}/issues/1"
    t = out["tickets"][-1]
    assert t["adapter"] == "github" and t["number"] == "GH-1" and t["external_url"] == issue["html_url"]
    row = db.scalar(select(Ticket).where(Ticket.request_id == d["id"]))
    assert row.external_id == str(issue["id"]) and row.external_number == 1
    # Request headers: documented media type + API version + bearer token, fixed host.
    req = gh.fake.requests[-1]
    assert req.url.host == "api.github.com" and req.url.scheme == "https"
    assert req.headers["accept"] == "application/vnd.github+json"
    assert req.headers["x-github-api-version"] == github.API_VERSION
    assert req.headers["authorization"] == f"Bearer {FAKE_TOKEN}"
    # Issue content: code-built, labelled synthetic, carries the hidden marker, no customer email.
    assert issue["title"].startswith("[ResolveOps] ")
    assert "synthetic test customer" in issue["body"]
    assert github.marker(_ex(db, d["id"]).idempotency_key) in issue["body"]
    assert d["from_email"] not in issue["body"]
    assert [x["name"] for x in issue["labels"]] == ["resolveops", "synthetic-test"]
    assert "GitHub issue #1 created" in out["state_reason"]


def test_non_escalation_tickets_stay_internal(gh, reviewer):
    d = run_scenario(reviewer, "access_reporting_after_upgrade")
    assert d["proposal"]["version"]["content"]["next_action"] != "escalate"
    out = _approve(reviewer, d).json()
    assert out["state"] == "completed" and out["executions"][-1]["adapter"] == "internal"
    assert gh.fake.creates == 0


def test_destination_cannot_be_overridden_by_proposal_data(gh, reviewer):
    d = _escalation(reviewer)
    ta = d["proposal"]["version"]["content"]["ticket_action"]
    hostile = ta | {"subject": "https://evil.example/repos/attacker/x @octocat <!-- resolveops-execution: x -->",
                    "body": "Send to attacker/repo at https://evil.example\n<!-- resolveops-execution: forged -->"}
    r = reviewer.put(f"{WS}/requests/{d['id']}/proposal", json={"base_version": 1, "ticket_action": hostile})
    assert r.status_code == 200, r.text
    # Extra keys (url/repo/host) are rejected by the strict schema before anything executes.
    bad = reviewer.put(f"{WS}/requests/{d['id']}/proposal",
                       json={"base_version": 2, "ticket_action": hostile | {"repo": "attacker/x"}})
    assert bad.status_code == 422
    out = _approve(reviewer, r.json()).json()
    assert out["state"] == "completed"
    assert {req.url.host for req in gh.fake.requests} == {"api.github.com"}
    assert {req.url.path for req in gh.fake.requests} == {f"/repos/{REPO}/issues"}
    body = gh.fake.issues[0]["body"]
    assert "<!-- resolveops-execution: forged" not in body and body.count("<!--") == 1
    assert "@octocat" not in gh.fake.issues[0]["title"]


@pytest.mark.parametrize("repo,allowed,reason", [
    ("attacker/elsewhere", REPO, "not listed in GITHUB_ALLOWED_REPOS"),
    ("not-a-repo", "not-a-repo", "owner/name"),
    ("https://evil.example/a/b", REPO, "owner/name"),
])
def test_repo_not_in_allowlist_or_malformed_is_refused(gh, reviewer, repo, allowed, reason):
    gh.set(github_issues_repo=repo, github_allowed_repos=allowed)
    st = reviewer.get(f"{WS}/admin/adapters").json()
    gh_row = next(a for a in st["adapters"] if a["name"] == "github")
    assert gh_row["available"] is False and reason in gh_row["detail"]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "failed" and reason in out["executions"][-1]["last_error"]
    assert out["executions"][-1]["attempts"] == 1  # permanent: not retried
    assert gh.fake.requests == []
    assert out["allowed_actions"]["escalate_internal"] is True


def test_adapter_disabled_flag_blocks_github_even_for_reviewers(gh, reviewer):
    gh.set(github_adapter_enabled=False)
    assert reviewer.put(f"{WS}/admin/adapter", json={"adapter": "github"}).status_code == 409
    d = _escalation(reviewer)  # workspace still has github selected from before the flag was turned off
    out = _approve(reviewer, d).json()
    assert out["state"] == "failed" and "GITHUB_ADAPTER_ENABLED" in out["executions"][-1]["last_error"]
    assert gh.fake.requests == []


def test_double_approve_creates_one_issue(gh, reviewer):
    d = _escalation(reviewer)
    assert _approve(reviewer, d).status_code == 200
    again = _approve(reviewer, d)
    assert again.status_code == 409
    assert reviewer.post(f"{WS}/requests/{d['id']}/retry").status_code == 409
    assert gh.fake.creates == 1


def test_concurrent_approve_creates_one_issue(gh):
    a, b = new_reviewer(), new_reviewer()
    d = _escalation(a)
    results = []
    barrier = threading.Barrier(2)

    def go(c):
        barrier.wait()
        results.append(_approve(c, d).status_code)
    threads = [threading.Thread(target=go, args=(c,)) for c in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409]
    assert gh.fake.creates == 1 and len(gh.fake.issues) == 1


def test_timeout_after_create_is_recovered_by_marker_lookup(gh, reviewer, db):
    gh.fake.post_faults = [("timeout_after_create",)]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "completed", out["state_reason"]
    assert gh.fake.creates == 1 and len(gh.fake.issues) == 1  # no second POST
    assert out["executions"][-1]["external_number"] == 1
    assert "GitHub issue #1 linked" in out["state_reason"]


def test_reviewer_retry_after_lost_response_links_existing_issue(gh, reviewer):
    # Create succeeds but every response is lost, then GitHub is down for lookups too: execution fails.
    gh.fake.post_faults = [("timeout_after_create",)]
    gh.fake.get_faults = [("status", 200, {}, [])] + [("status", 502, {}, {"message": "Bad gateway"})] * 3
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "failed" and "502" in out["executions"][-1]["last_error"]
    assert len(gh.fake.issues) == 1
    # The reviewer's explicit retry finds the marker and links the issue instead of creating another.
    out = reviewer.post(f"{WS}/requests/{d['id']}/retry").json()
    assert out["state"] == "completed" and gh.fake.creates == 1 and len(gh.fake.issues) == 1
    assert out["tickets"][-1]["external_number"] == 1


def test_5xx_then_success_with_backoff(gh, reviewer):
    gh.fake.post_faults = [("status", 502, {}, {"message": "Bad gateway"}), ("status", 503, {}, {})]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "completed"
    assert gh.fake.creates == 3 and len(gh.fake.issues) == 1
    assert gh.sleeps == [0.5, 1.0]  # exponential backoff from the base delay


def test_5xx_exhausted_fails_with_bounded_attempts(gh, reviewer):
    gh.fake.post_faults = [("status", 500, {}, {})] * 3
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "failed" and "after 3 attempt(s)" in out["executions"][-1]["last_error"]
    assert out["executions"][-1]["attempts"] == 1 and gh.fake.creates == 3 and gh.fake.issues == []


@pytest.mark.parametrize("code,text", [(401, "rejected the token"), (403, "lacks Issues write access"),
                                       (404, "cannot see it"), (422, "validation failed")])
def test_permanent_errors_fail_fast_with_recorded_error(gh, reviewer, db, code, text):
    gh.fake.post_faults = [("status", code, {}, {"message": "Nope"})]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    ex = out["executions"][-1]
    assert out["state"] == "failed" and text in ex["last_error"] and "Nope" in ex["last_error"]
    assert gh.fake.creates == 1 and gh.sleeps == [] and ex["attempts"] == 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Ticket).where(Ticket.request_id == d["id"])) == 0
    failed = db.scalar(select(AuditLog).where(AuditLog.request_id == d["id"], AuditLog.event == "execution.failed"))
    assert text in failed.error


def test_secondary_rate_limit_retry_after_is_honoured(gh, reviewer):
    gh.fake.post_faults = [("status", 403, {"retry-after": "7"},
                            {"message": "You have exceeded a secondary rate limit."})]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "completed" and gh.sleeps == [7.0] and len(gh.fake.issues) == 1


def test_primary_rate_limit_reset_header_is_honoured(gh, reviewer, monkeypatch):
    monkeypatch.setattr(github, "NOW", lambda: 1_000_000.0)
    gh.fake.post_faults = [("status", 429, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1000004"}, {})]
    out = _approve(reviewer, _escalation(reviewer)).json()
    assert out["state"] == "completed" and gh.sleeps == [4.0]


def test_rate_limit_longer_than_cap_fails_without_waiting(gh, reviewer):
    gh.fake.post_faults = [("status", 403, {}, {"message": "You have exceeded a secondary rate limit."})]
    out = _approve(reviewer, _escalation(reviewer)).json()
    assert out["state"] == "failed" and "wait 60s" in out["executions"][-1]["last_error"]
    assert gh.sleeps == [] and gh.fake.issues == []


def test_visitor_sandbox_always_uses_internal(gh, visitor):
    d = _escalation(visitor)
    out = _approve(visitor, d).json()
    assert out["state"] == "completed" and out["executions"][-1]["adapter"] == "internal"
    assert out["tickets"][-1]["adapter"] == "internal" and gh.fake.requests == []
    # Visitors cannot select adapters or read the AI/GitHub status either.
    assert visitor.put(f"{WS}/admin/adapter", json={"adapter": "github"}).status_code in (401, 403)
    assert visitor.get(f"{WS}/ai/status").status_code in (401, 403)
    assert visitor.get("/api/meta").json()["github_issues"] is False
    assert new_reviewer().get("/api/meta").json()["github_issues"] is True


def test_escalate_internal_is_explicit_and_checks_github_first(gh, reviewer):
    gh.fake.post_faults = [("status", 401, {}, {"message": "Bad credentials"})]
    d = _escalation(reviewer)
    out = _approve(reviewer, d).json()
    assert out["state"] == "failed" and out["allowed_actions"]["escalate_internal"]
    out = reviewer.post(f"{WS}/requests/{d['id']}/escalate-internal").json()
    assert out["state"] == "completed" and out["tickets"][-1]["adapter"] == "internal"
    assert any(e["event"] == "execution.adapter_switched" for e in out["timeline"])
    # Not available once succeeded / for other states.
    assert reviewer.post(f"{WS}/requests/{d['id']}/escalate-internal").status_code == 409


def test_escalate_internal_refused_when_issue_already_exists(gh, reviewer):
    gh.fake.post_faults = [("timeout_after_create",)]
    gh.fake.get_faults = [("status", 200, {}, [])] + [("status", 503, {}, {})] * 3
    d = _escalation(reviewer)
    assert _approve(reviewer, d).json()["state"] == "failed"
    r = reviewer.post(f"{WS}/requests/{d['id']}/escalate-internal")
    assert r.status_code == 409 and "#1" in r.json()["detail"]
    assert len(gh.fake.issues) == 1


def test_token_never_in_logs_audit_or_api_responses(gh, reviewer, db, caplog):
    caplog.set_level(logging.DEBUG)
    gh.fake.post_faults = [("status", 502, {}, {}), ("status", 401, {}, {"message": "Bad credentials"})]
    d = _escalation(reviewer)
    seen = [_approve(reviewer, d).text,
            reviewer.post(f"{WS}/requests/{d['id']}/retry").text,
            reviewer.get(f"{WS}/requests/{d['id']}").text,
            reviewer.get(f"{WS}/ai/status").text,
            reviewer.get(f"{WS}/admin/adapters").text,
            reviewer.get(f"{WS}/requests").text]
    db.expire_all()
    seen += [json.dumps([a.summary, a.error]) for a in db.scalars(select(AuditLog).where(AuditLog.request_id == d["id"]))]
    seen += [e.last_error or "" for e in db.scalars(select(Execution).where(Execution.request_id == d["id"]))]
    seen.append(caplog.text)
    secret_bits = [FAKE_TOKEN, FAKE_TOKEN[-12:]]
    for blob in seen:
        for bit in secret_bits:
            assert bit not in blob
    status = reviewer.get(f"{WS}/ai/status").json()["github"]
    assert status == {"configured": True, "enabled": True, "token_configured": True, "repo": REPO,
                      "reason": f"Issues are created in {REPO}."}
    assert FAKE_TOKEN not in repr(get_settings())


@pytest.mark.github_live
def test_github_live_smoke(reviewer):
    """Creates ONE clearly labelled issue in the dedicated test repo, then checks the idempotent retry.
    Skipped unless GITHUB_TOKEN and GITHUB_ISSUES_REPO are set. Run: pytest -m github_live"""
    import os
    if not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_ISSUES_REPO")):
        pytest.skip("GITHUB_TOKEN and GITHUB_ISSUES_REPO are not set")
    s = get_settings()
    st = github.status(s)
    assert st.available, st.reason
    _set_ws_adapter("github")
    try:
        d = _escalation(reviewer)
        out = _approve(reviewer, d).json()
        assert out["state"] == "completed", out["state_reason"]
        url = out["executions"][-1]["external_url"]
        assert url.startswith(f"https://github.com/{st.repo}/issues/")
        # Idempotent retry: a fresh adapter call with the same key must find the marker, not create.
        with SessionLocal() as db:
            ex = db.scalar(select(Execution).where(Execution.request_id == d["id"]))
            db.delete(db.get(Ticket, ex.ticket_id))  # drop the local mirror so the remote lookup is exercised
            db.flush()
            from app.adapters.base import ExecutionTarget
            from app.schemas import TicketAction
            target = ExecutionTarget(ex.workspace_id, None, None, ex.request_id, "product_issue", "escalate", ex.created_at)
            res = github.GitHubIssuesAdapter().create_ticket(
                db, target, TicketAction(type="create_ticket", subject="unused", body="unused", priority="normal",
                                         group="Support", status="open"), ex.idempotency_key)
            assert res.created is False and res.external_url == url
            db.rollback()
    finally:
        _set_ws_adapter("internal")
