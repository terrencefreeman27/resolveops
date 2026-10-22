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


def _escape(text: str | None, limit: int, markdown: bool = True) -> str:
    """Neutralise markup that could ping people, embed HTML/comments (forge a marker), or break layout.
    Titles are plain text on GitHub (markdown=False): single line, no HTML escaping needed."""
    t = (text or "").replace("\r\n", "\n")
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", t)
    if markdown:
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    else:
        t = re.sub(r"\s+", " ", t).strip()
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
    title = _escape(action.subject or (req.subject if req else "Escalation"), MAX_TITLE - 13, markdown=False)
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


# --- HTTP ------------------------------------------------------------------------------------

FATAL = {
    400: "GitHub rejected the request as malformed (400)",
    401: "GitHub rejected the token (401): it is invalid, expired or revoked",
    403: "GitHub refused the request (403): the token lacks Issues write access to this repository",
    404: "GitHub returned 404: the repository does not exist or the token cannot see it",
    410: "GitHub returned 410: issues are disabled for this repository",
    422: "GitHub rejected the issue (422 validation failed or spam protection)",
}


def _gh_message(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("message", "")
    except Exception:  # noqa: BLE001 - non-JSON error body
        msg = ""
    return re.sub(r"\s+", " ", str(msg))[:200]


def rate_limit_wait(resp: httpx.Response, now: float | None = None) -> float | None:
    """Seconds to wait before retrying a 403/429, or None if it is not a rate limit.
    Follows GitHub's documented order: retry-after, then x-ratelimit-remaining=0 + reset, else 60s."""
    ra = resp.headers.get("retry-after")
    if ra is not None:
        try:
            return max(0.0, float(ra))
        except ValueError:
            return 60.0
    if resp.headers.get("x-ratelimit-remaining") == "0":
        try:
            return max(0.0, float(resp.headers.get("x-ratelimit-reset", "")) - (now or time.time()))
        except ValueError:
            return 60.0
    if "rate limit" in _gh_message(resp).lower():
        return 60.0
    return None


class _Client:
    """Bounded retries around one repository. The token only ever lives in the Authorization header."""

    def __init__(self, settings: Settings, owner: str, name: str):
        self.s = settings
        self.path = f"/repos/{owner}/{name}/issues"
        self.repo = f"{owner}/{name}"
        self.http = httpx.Client(
            base_url=API_BASE, transport=TRANSPORT, timeout=settings.github_timeout_s, follow_redirects=False,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
                     "User-Agent": "ResolveOps-ticket-adapter",
                     "Authorization": f"Bearer {settings.github_token.get_secret_value()}"})

    def close(self) -> None:
        self.http.close()

    def _once(self, send) -> tuple[bool, object, float | None]:
        """(ok, json-or-reason, wait). Raises GitHubError(retryable=False) for permanent failures."""
        try:
            resp = send()
        except httpx.TimeoutException:
            return False, f"timed out after {self.s.github_timeout_s:g}s (outcome unknown)", None
        except httpx.TransportError as exc:
            return False, f"network error ({type(exc).__name__})", None
        if 200 <= resp.status_code < 300:
            return True, resp.json(), None
        if resp.status_code in (403, 429):
            wait = rate_limit_wait(resp)
            if wait is not None:
                if wait > self.s.github_max_wait_s:
                    raise GitHubError(f"GitHub rate limit hit ({resp.status_code}); GitHub asks to wait "
                                      f"{int(wait)}s. Nothing was created; retry later.", retryable=False)
                return False, f"rate limited ({resp.status_code}), waited {wait:g}s", wait
        if resp.status_code >= 500:
            return False, f"GitHub server error {resp.status_code}", None
        base = FATAL.get(resp.status_code, f"GitHub returned {resp.status_code}")
        detail = _gh_message(resp)
        raise GitHubError(f"{base}{': ' + detail if detail else ''}.", retryable=False)

    def call(self, what: str, send, before_retry=None):
        last = ""
        for attempt in range(1, self.s.github_max_attempts + 1):
            if attempt > 1 and before_retry is not None:
                found = before_retry()
                if found is not None:
                    return found
            ok, value, wait = self._once(send)
            if ok:
                return value
            last = str(value)
            log.warning("github %s attempt %d failed: %s", what, attempt, last)
            if attempt < self.s.github_max_attempts:
                SLEEP(wait if wait is not None else min(self.s.github_retry_base_delay_s * 2 ** (attempt - 1),
                                                        self.s.github_max_wait_s))
        raise GitHubError(f"GitHub {what} failed after {self.s.github_max_attempts} attempt(s): {last}.",
                          retryable=False)

    def find(self, key: str, since: datetime | None) -> dict | None:
        """An issue in the configured repository whose body carries this execution's marker."""
        needle = marker(key)
        params = {"state": "all", "sort": "created", "direction": "desc", "per_page": 100}
        if since is not None:
            params["since"] = (since - timedelta(minutes=5)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for page in range(1, LOOKUP_PAGES + 1):
            items = self.call("issue lookup", lambda p=page: self.http.get(self.path, params={**params, "page": p}))
            if not isinstance(items, list):
                raise GitHubError("GitHub issue lookup returned an unexpected response.", retryable=False)
            for it in items:
                if isinstance(it, dict) and "pull_request" not in it and needle in (it.get("body") or ""):
                    return it
            if len(items) < 100:
                return None
        return None

    def create(self, payload: dict, key: str, since: datetime | None) -> tuple[dict, str]:
        """Returns (issue, how): how is "created", "existing" (found before sending), or
        "recovered" (an earlier send whose response was lost turned out to have created it)."""
        existing = self.find(key, since)
        if existing is not None:
            return existing, "existing"
        recovered = {}

        def recheck():
            found = self.find(key, since)
            if found is not None:
                recovered["yes"] = True
            return found
        issue = self.call("create issue", lambda: self.http.post(self.path, json=payload), before_retry=recheck)
        return issue, "recovered" if recovered else "created"


# --- adapter ---------------------------------------------------------------------------------

def _valid_issue(issue: object, repo: str) -> tuple[int, int, str]:
    """Only accept a well-formed issue that links back to the configured repository."""
    if not isinstance(issue, dict):
        raise GitHubError("GitHub returned an unexpected response.", retryable=False)
    number, iid, url = issue.get("number"), issue.get("id"), issue.get("html_url")
    prefix = f"https://github.com/{repo}/issues/".lower()
    if not (isinstance(number, int) and isinstance(iid, int) and isinstance(url, str)
            and url.lower() == f"{prefix}{number}"):
        raise GitHubError("GitHub returned an issue that does not match the configured repository.", retryable=False)
    return number, iid, url


class GitHubIssuesAdapter(TicketAdapter):
    """Creates one GitHub issue per approved escalation and mirrors it as a local ticket row
    (adapter="github", external number/id/url, same UNIQUE idempotency key)."""
    name = "github"

    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()

    def _guard(self, target: ExecutionTarget) -> tuple[str, str]:
        if target.demo_session_id is not None:  # defence in depth: review.py already routes visitors to internal
            raise GitHubError("Visitor sandboxes never use external adapters.", retryable=False)
        st = status(self.s)
        if not st.available:
            raise GitHubError(f"GitHub Issues adapter unavailable: {st.reason}", retryable=False)
        return parse_repo(self.s.github_issues_repo)

    def create_ticket(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult:
        mirror = db.scalar(select(Ticket).where(Ticket.idempotency_key == idempotency_key))
        if mirror is not None:
            return TicketResult(mirror.id, mirror.number, False, mirror.external_id, mirror.external_url,
                                mirror.external_number)
        owner, name = self._guard(target)
        payload = build_issue(db, target, action, idempotency_key, self.s)
        client = _Client(self.s, owner, name)
        try:
            issue, how = client.create(payload, idempotency_key, target.not_before)
        finally:
            client.close()
        number, iid, url = _valid_issue(issue, client.repo)
        log.info("github issue %s#%d %s for execution %s", client.repo, number, how, idempotency_key[:12])
        t = Ticket(
            workspace_id=target.workspace_id, demo_session_id=None, customer_id=target.customer_id,
            request_id=target.request_id, number=f"GH-{number}", subject=action.subject or payload["title"],
            body=action.body or "", category=target.category, priority=action.priority or "normal",
            status=action.status or "open", group=action.group or "", source="execution", adapter=self.name,
            external_id=str(iid), external_url=url, external_number=number, idempotency_key=idempotency_key)
        db.add(t)
        db.flush()
        return TicketResult(t.id, t.number, how == "created", str(iid), url, number)

    def add_note(self, db: Session, target: ExecutionTarget, action: TicketAction, idempotency_key: str) -> TicketResult:
        # Notes stay internal in M4 (review.py never routes add_note here); refuse rather than guess.
        raise GitHubError("The GitHub adapter only creates issues for escalations.", retryable=False)

    def find_existing(self, target: ExecutionTarget, idempotency_key: str) -> dict | None:
        """Read-only marker lookup, used before an explicit fallback to the internal adapter."""
        owner, name = self._guard(target)
        client = _Client(self.s, owner, name)
        try:
            return client.find(idempotency_key, target.not_before)
        finally:
            client.close()
