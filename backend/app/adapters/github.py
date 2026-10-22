"""Optional GitHub Issues adapter (SPEC §10, docs/DECISIONS.md D28-D30).

Destination: fixed base URL + one server-configured repository that must also be allowlisted.
Nothing from a proposal (model output or reviewer edit) can change the host, URL, or repository;
proposal fields only become the escaped issue title/body.

Idempotency: every issue body carries a hidden marker `<!-- resolveops-execution: <key> -->`.
Before creating, and before every re-send after an ambiguous failure (timeout, network error, 5xx),
the adapter lists the repository's recently updated issues (the List repository issues endpoint,
not the search API, whose index lags) and reuses an issue carrying the marker.

UNVERIFIED against real GitHub: tests use a fake HTTP transport. See README.
"""
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Customer, SupportRequest, Ticket, Workspace
from ..schemas import TicketAction
from .base import AdapterError, ExecutionTarget, TicketAdapter, TicketResult

log = logging.getLogger("resolveops.github")

API_BASE = "https://api.github.com"  # fixed; never read from data or config
API_VERSION = "2026-03-10"  # current version listed by GET https://api.github.com/versions (checked 2026-10-22)
MARKER_PREFIX = "<!-- resolveops-execution: "
MAX_TITLE = 200
MAX_BODY = 20_000  # well under GitHub's 65,536-character body limit
LOOKUP_PAGES = 3  # x 100 issues updated since the execution started

OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9 _.:/-]{1,50}$")

# Test hooks (never set from input): an httpx transport and a sleep function.
TRANSPORT: httpx.BaseTransport | None = None
SLEEP = time.sleep


class GitHubError(AdapterError):
    pass


def parse_repo(value: str) -> tuple[str, str] | None:
    parts = value.strip().split("/")
    if len(parts) != 2:
        return None
    owner, name = parts
    if not OWNER_RE.match(owner) or not NAME_RE.match(name) or name in (".", "..") or name.endswith(".git"):
        return None
    return owner, name


@dataclass(frozen=True)
class GitHubStatus:
    enabled: bool
    token_configured: bool
    repo: str | None  # the configured destination, shown to reviewers; never the token
    available: bool
    reason: str


def status(settings: Settings | None = None) -> GitHubStatus:
    s = settings or get_settings()
    token = bool(s.github_token.get_secret_value())
    parsed = parse_repo(s.github_issues_repo) if s.github_issues_repo else None
    repo = f"{parsed[0]}/{parsed[1]}" if parsed else None
    allowed = {r.strip().lower() for r in s.github_allowed_repos.split(",") if r.strip()}

    def out(ok: bool, reason: str) -> GitHubStatus:
        return GitHubStatus(s.github_adapter_enabled, token, repo, ok, reason)

    if not s.github_adapter_enabled:
        return out(False, "Disabled on this server (GITHUB_ADAPTER_ENABLED is not true).")
    if not token:
        return out(False, "GITHUB_TOKEN is not set on the server.")
    if not s.github_issues_repo:
        return out(False, "GITHUB_ISSUES_REPO is not set on the server.")
    if parsed is None:
        return out(False, "GITHUB_ISSUES_REPO must be in owner/name form.")
    if repo.lower() not in allowed:
        return out(False, "GITHUB_ISSUES_REPO is not listed in GITHUB_ALLOWED_REPOS.")
    return out(True, f"Issues are created in {repo}.")


def marker(key: str) -> str:
    return f"{MARKER_PREFIX}{key} -->"


def _escape(text: str | None, limit: int) -> str:
    """Neutralise markup that could ping people, embed HTML/comments (forge a marker), or break layout."""
    t = (text or "").replace("\r\n", "\n")
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", t)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = t.replace("@", "@​")  # no @mentions / team pings
    return t if len(t) <= limit else t[: limit - 1] + "…"


def labels(settings: Settings) -> list[str]:
    out = [x.strip() for x in settings.github_labels.split(",") if x.strip()]
    return [x for x in out if LABEL_RE.match(x)][:10]


def build_issue(db: Session, target: ExecutionTarget, action: TicketAction, key: str, settings: Settings) -> dict:
    """Title and body are built by code from approved proposal fields. Deliberately excluded:
    customer email, the customer's original message, the draft reply, reviewer identity,
    retrieved passages and scores, internal ids other than the request reference."""
    ws = db.get(Workspace, target.workspace_id)
    req = db.get(SupportRequest, target.request_id)
    cust = db.get(Customer, target.customer_id) if target.customer_id else None
    if cust is None:
        who = "No linked customer"
    else:
        who = f"{_escape(cust.company_name, 120)} ({_escape(cust.account_ref, 40)})"
        if cust.is_synthetic:
            who += " — synthetic test customer, not a real account"
    title = _escape(action.subject or (req.subject if req else "Escalation"), MAX_TITLE - 13)
    body = "\n".join([
        f"**Escalated from ResolveOps** — {_escape(ws.name, 120)}",
        "",
        f"- **Category:** {_escape(target.category, 32)}",
        f"- **Priority:** {_escape(action.priority, 16)}",
        f"- **Group:** {_escape(action.group, 64)}",
        f"- **Customer:** {who}",
        "",
        "### Summary for the team",
        "",
        _escape(action.body, 8000),
        "",
        "---",
        f"Approved by a ResolveOps reviewer. Request reference: `{target.request_id}`.",
        marker(key),
    ])
    payload = {"title": f"[ResolveOps] {title}", "body": body[:MAX_BODY]}
    if labels(settings):
        payload["labels"] = labels(settings)
    return payload
