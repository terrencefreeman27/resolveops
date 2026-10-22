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
