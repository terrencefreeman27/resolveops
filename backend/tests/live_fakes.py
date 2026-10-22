"""A fake Anthropic client for live-provider tests.

It exposes the one SDK surface the live provider uses — `client.beta.messages.create(**params)` —
and returns objects shaped like SDK responses (content blocks, stop_reason, usage, model). A
script is a list of steps; each step is a response, an exception to raise, or a callable that
builds a response from the request params (used to cite chunk ids that retrieval really returned).

Recorded fixtures live in tests/fixtures/live/*.json: turn-by-turn responses in the Messages API
response shape. They are hand-written in that shape (no API key exists on the build machine), not
captured from the real API. "{{cite:<doc-slug>}}" placeholders resolve to a chunk id that the
conversation's search_knowledge_base results actually contained.
"""
import itertools
import json
import re
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2

FIXTURES = Path(__file__).parent / "fixtures" / "live"
_ids = itertools.count(1)
PASSAGE_RE = re.compile(r'<passage chunk_id="([0-9a-f-]{36})" doc="([^"]+)" version="\d+" section="([^"]*)"')


def usage(inp: int = 1000, out: int = 200, cache_read: int = 0) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=cache_read,
                           cache_creation_input_tokens=0)


def response(content: list, stop_reason: str, inp: int = 1000, out: int = 200, model: str = "claude-opus-5-5",
             stop_details=None) -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=stop_details,
                           usage=usage(inp, out), model=model)


def tool_use(name: str, inp: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids):04d}", name=name, input=inp)


def text(obj) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=obj if isinstance(obj, str) else json.dumps(obj))


def thinking() -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking="", signature="sig")


def tool_turn(*calls: tuple[str, dict], inp: int = 1500, out: int = 120) -> SimpleNamespace:
    return response([thinking(), *(tool_use(n, a) for n, a in calls)], "tool_use", inp, out)


def tool_results_text(params: dict) -> str:
    """All tool_result contents the model has been sent so far."""
    out = []
    for m in params["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            out.extend(r["content"] for r in m["content"] if r.get("type") == "tool_result")
    return "\n".join(out)


def passages_seen(params: dict) -> list[tuple[str, str, str]]:
    return PASSAGE_RE.findall(tool_results_text(params))


def resolve_cites(obj, params: dict):
    seen = passages_seen(params)

    def sub(v):
        if isinstance(v, str):
            m = re.fullmatch(r"\{\{cite:([a-z0-9-]+)\}\}", v)
            if m:
                return next(cid for cid, slug, _ in seen if slug == m.group(1))
            return v
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v
    return sub(obj)


def final_turn(final: dict, inp: int = 4000, out: int = 600):
    """A final structured-output turn; {{cite:slug}} placeholders resolve against real retrieval."""
    return lambda params: response([thinking(), text(resolve_cites(final, params))], "end_turn", inp, out)


def load_fixture(name: str) -> list:
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    steps = []
    for t in data["turns"]:
        u = t.get("usage", {})
        if t["stop_reason"] == "tool_use":
            steps.append(tool_turn(*[(c["name"], c["input"]) for c in t["tool_calls"]],
                                   inp=u.get("input_tokens", 1500), out=u.get("output_tokens", 120)))
        else:
            steps.append(final_turn(t["final"], inp=u.get("input_tokens", 4000), out=u.get("output_tokens", 600)))
    return steps


def fixture_tokens(name: str) -> tuple[int, int]:
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    return (sum(t["usage"]["input_tokens"] for t in data["turns"]),
            sum(t["usage"]["output_tokens"] for t in data["turns"]))


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def api_error(cls, status: int, retry_after: str | None = "0"):
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return cls(f"simulated {status}", response=httpx2.Response(status, request=_REQ, headers=headers), body=None)


def timeout_error():
    return anthropic.APITimeoutError(request=_REQ)


class FakeAnthropic:
    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        # Snapshot the conversation as sent (the provider appends to the same list afterwards).
        self.calls.append({**params, "messages": list(params["messages"])})
        if not self.script:
            raise AssertionError("FakeAnthropic: script exhausted")
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return step(params)
        return step
