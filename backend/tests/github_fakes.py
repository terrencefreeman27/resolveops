"""In-memory fake of the two GitHub REST endpoints the adapter uses (no network, no real token).

Scripted faults are consumed in order by POST (create) or GET (list) calls:
  ("status", code, headers, json)  -> return that response without creating anything
  ("timeout_after_create",)        -> create the issue, then raise a read timeout (response lost)
  ("timeout",)                     -> raise a connect timeout before anything happens
"""
import json

import httpx

FAKE_TOKEN = "github_pat_TEST_ONLY_not_a_real_token_0123456789"
REPO = "resolveops-test/sandbox"


class FakeGitHub:
    def __init__(self, repo: str = REPO):
        self.repo = repo
        self.issues: list[dict] = []
        self.requests: list[httpx.Request] = []
        self.post_faults: list[tuple] = []
        self.get_faults: list[tuple] = []
        self.next_id = 9_000_001

    @property
    def creates(self) -> int:
        return sum(1 for r in self.requests if r.method == "POST")

    def _create(self, payload: dict) -> dict:
        n = len(self.issues) + 1
        issue = {"id": self.next_id + n, "number": n, "title": payload["title"], "body": payload.get("body"),
                 "labels": [{"name": x} for x in payload.get("labels", [])], "state": "open",
                 "html_url": f"https://github.com/{self.repo}/issues/{n}"}
        self.issues.append(issue)
        return issue

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = f"/repos/{self.repo}/issues"
        if request.url.host != "api.github.com" or request.url.path != path:
            return httpx.Response(404, json={"message": "Not Found"})
        faults = self.post_faults if request.method == "POST" else self.get_faults
        if faults:
            fault = faults.pop(0)
            if fault[0] == "status":
                _, code, headers, body = fault
                return httpx.Response(code, headers=headers, json=body)
            if fault[0] == "timeout":
                raise httpx.ConnectTimeout("simulated", request=request)
            if fault[0] == "timeout_after_create":
                self._create(json.loads(request.content))
                raise httpx.ReadTimeout("simulated", request=request)
        if request.method == "POST":
            return httpx.Response(201, json=self._create(json.loads(request.content)))
        newest_first = list(reversed(self.issues))
        page, per = int(request.url.params.get("page", 1)), int(request.url.params.get("per_page", 30))
        return httpx.Response(200, json=newest_first[(page - 1) * per: page * per])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
