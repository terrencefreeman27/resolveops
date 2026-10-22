"""Live provider: Claude via the official `anthropic` SDK, with tool use and structured output.

Flow for one request (run_agent):
  1. One user message holds the escaped customer message plus trusted server context.
  2. Bounded loop: the model may call allowlisted tools; each call goes through ToolGate, which
     enforces the allowlist, authority and cross-customer rules in code, then tools.call_tool.
  3. When the model stops calling tools, its final message is JSON constrained by
     `output_config.format` and validated again with the Pydantic schemas (extra fields forbidden).

Failure handling: bounded retries with exponential backoff for retryable errors (429, 5xx incl.
529 overloaded, timeouts, connection errors); everything else fails at once. Any failure raises
ProviderError — the workflow puts the request in `error`. There is no simulated fallback.

Secrets: the API key is read from settings and handed to the SDK client only. It is never logged,
returned, audited, or placed in a prompt.
"""
import json
import random
import time
from collections.abc import Callable
from dataclasses import replace

import anthropic
from pydantic import ValidationError
from sqlalchemy import select

from .. import audit
from ..config import Settings, get_settings
from ..models import Customer, SupportRequest, Workspace
from ..schemas import Classification, ProposalDraft, Strict
from ..tools import ToolContext
from .base import AgentResult, AIProvider, ProviderError, SynthesisInput, Usage
from .live_guard import ToolGate
from .live_prompt import FINAL_OUTPUT_SCHEMA, SYSTEM_PROMPT, TOOL_DEFINITIONS, first_user_message

FALLBACK_BETA = "server-side-fallback-2026-07-01"
RETRYABLE_STATUS = {408, 409, 429}


def label_for(model: str) -> str:
    return f"Live — Claude {model}"


def default_client_factory(settings: Settings):
    # SDK-level retries are off: retries are done (and audited) by LiveProvider._call.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0, timeout=settings.live_call_timeout_s)


# Tests replace this with a fake client factory. Production uses the real SDK client.
client_factory: Callable[[Settings], object] = default_client_factory


class _ClassificationOut(Strict):
    category: str
    priority: str
    justification: str
    summary: str
    mentioned_emails: list[str]
    risk_flags: list[str]


class FinalOutput(Strict):
    classification: _ClassificationOut
    proposal: ProposalDraft


class LiveProvider(AIProvider):
    name = "claude"
    simulated = False
    agentic = True

    def __init__(self, settings: Settings | None = None, client=None, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings or get_settings()
        if not self.settings.anthropic_api_key:
            raise ProviderError("Live mode: ANTHROPIC_API_KEY not configured. Add it to .env on the server and "
                                "restart the API, or set AI_MODE=demo. No simulated output was substituted.")
        self.model = self.settings.live_model
        self.label = label_for(self.model)
        self.client = client if client is not None else client_factory(self.settings)
        self._sleep = sleep

    # The step-wise interface is not used in live mode: the model drives its own tool loop.
    def classify(self, subject: str, body: str) -> Classification:  # pragma: no cover
        raise ProviderError("Live provider uses run_agent().")

    def synthesize(self, inp: SynthesisInput) -> ProposalDraft:  # pragma: no cover
        raise ProviderError("Live provider uses run_agent().")

    # --- one API call with bounded retries -------------------------------------------------

    def _request_params(self, messages: list) -> dict:
        s = self.settings
        params = dict(
            model=self.model,
            max_tokens=s.live_max_output_tokens,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": s.live_effort,
                           "format": {"type": "json_schema", "schema": FINAL_OUTPUT_SCHEMA}},
            cache_control={"type": "ephemeral"},
        )
        if s.live_refusal_fallback:
            params |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return params

    def _call(self, ctx: ToolContext, messages: list, usage: Usage):
        s = self.settings
        attempts = s.live_max_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                resp = self.client.beta.messages.create(**self._request_params(messages))
                usage.api_calls += 1
                return resp
            except anthropic.AuthenticationError as exc:
                raise ProviderError("Live provider rejected the API key (401 authentication_error). "
                                    "Check ANTHROPIC_API_KEY on the server.") from exc
            except anthropic.PermissionDeniedError as exc:
                raise ProviderError(f"Live provider denied the request (403): {exc.message}") from exc
            except anthropic.NotFoundError as exc:
                raise ProviderError(f"Live provider: model '{self.model}' not found (404). Check LIVE_MODEL.") from exc
            except anthropic.BadRequestError as exc:
                raise ProviderError(f"Live provider rejected the request (400): {exc.message}") from exc
            except anthropic.APIStatusError as exc:
                retryable = exc.status_code in RETRYABLE_STATUS or exc.status_code >= 500
                err = f"{exc.status_code} {getattr(exc, 'type', None) or 'api_error'}"
                retry_after = _retry_after(exc)
                if not retryable:
                    raise ProviderError(f"Live provider error ({err}): {exc.message}") from exc
            except anthropic.APIConnectionError as exc:  # includes APITimeoutError
                err = "timeout" if isinstance(exc, anthropic.APITimeoutError) else "connection error"
                retry_after = None
            except anthropic.APIError as exc:  # e.g. a response that failed SDK validation
                raise ProviderError(f"Live provider returned an invalid response: {str(exc)[:200]}") from exc
            elapsed = int((time.perf_counter() - started) * 1000)
            if attempt == attempts:
                audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="ai.call_failed",
                             request_id=ctx.request_id, demo_session_id=ctx.demo_session_id, duration_ms=elapsed,
                             summary={"attempt": attempt, "of": attempts}, error=err)
                raise ProviderError(f"Live provider unavailable after {attempts} attempt(s) (last error: {err}). "
                                    "The request was not processed; reprocess it later.")
            delay = min(s.live_retry_max_delay_s, s.live_retry_base_delay_s * 2 ** (attempt - 1))
            delay = min(s.live_retry_max_delay_s, max(delay, retry_after or 0)) + random.uniform(0, delay / 4)
            usage.retries += 1
            audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="ai.retry",
                         request_id=ctx.request_id, demo_session_id=ctx.demo_session_id, duration_ms=elapsed,
                         summary={"attempt": attempt, "of": attempts, "backoff_s": round(delay, 2)}, error=err)
            self._sleep(delay)
        raise ProviderError("unreachable")  # pragma: no cover

    # --- the bounded tool loop ---------------------------------------------------------------

    def run_agent(self, ctx: ToolContext, subject: str, body: str) -> AgentResult:
        ctx = replace(ctx, actor=f"ai:{self.name}")  # tool calls in the timeline are attributed to the model
        usage = Usage(model=self.model)
        try:
            return self._loop(ctx, subject, body, usage)
        except ProviderError as exc:
            exc.usage = usage  # tokens already spent still count toward the budget
            raise

    def _loop(self, ctx: ToolContext, subject: str, body: str, usage: Usage) -> AgentResult:
        s = self.settings
        gate = ToolGate(ctx)
        messages: list = [{"role": "user", "content": self._first_message(ctx, subject, body)}]
        tool_turns = 0
        while True:
            resp = self._call(ctx, messages, usage)
            self._add_usage(usage, resp)
            if usage.total_tokens > s.live_max_tokens_per_request:
                raise ProviderError(f"Live request exceeded the per-request token limit "
                                    f"({usage.total_tokens} > {s.live_max_tokens_per_request}).")
            stop = getattr(resp, "stop_reason", None)
            if stop == "refusal":
                details = getattr(resp, "stop_details", None)
                cat = getattr(details, "category", None) if details else None
                raise ProviderError(f"Live model declined the request (refusal{f': {cat}' if cat else ''}). "
                                    "A human should handle it.")
            if stop == "max_tokens":
                raise ProviderError(f"Live model hit the output limit ({s.live_max_output_tokens} tokens) "
                                    "before finishing. Raise LIVE_MAX_OUTPUT_TOKENS or reprocess.")
            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            if stop == "tool_use" and tool_uses:
                if tool_turns >= s.live_max_tool_steps:
                    audit.record(ctx.db, workspace_id=ctx.workspace_id, actor=ctx.actor, event="ai.tool_limit",
                                 request_id=ctx.request_id, demo_session_id=ctx.demo_session_id,
                                 summary={"max_tool_steps": s.live_max_tool_steps, "tool_calls": usage.tool_steps},
                                 error="Tool-call step limit reached.")
                    raise ProviderError(f"Live model exceeded the tool-call limit ({s.live_max_tool_steps} steps) "
                                        "without finishing. The request needs human handling or a reprocess.")
                tool_turns += 1
                messages.append({"role": "assistant", "content": resp.content})  # append-only history
                results = []
                for tu in tool_uses:
                    usage.tool_steps += 1
                    outcome = gate.run(tu.name, tu.input)
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": outcome.content,
                                    **({"is_error": True} if outcome.is_error else {})})
                messages.append({"role": "user", "content": results})  # all results in one message
                continue
            if stop != "end_turn":
                raise ProviderError(f"Live model stopped unexpectedly (stop_reason={stop}).")
            final = self._parse_final(resp)
            return self._result(final, gate, usage)

    # --- helpers -----------------------------------------------------------------------------

    def _first_message(self, ctx: ToolContext, subject: str, body: str) -> str:
        ws = ctx.db.get(Workspace, ctx.workspace_id)
        cust = ctx.db.get(Customer, ctx.customer_id) if ctx.customer_id else None
        req = ctx.db.get(SupportRequest, ctx.request_id) if ctx.request_id else None
        label = f"{cust.company_name} ({cust.account_ref}), contact {cust.contact_name}" if cust else "none"
        return first_user_message(
            workspace_name=ws.name, profile=ws.profile or {}, ticket_groups=ws.settings.get("ticket_groups", []),
            categories=ws.settings.get("supported_categories", ["access", "billing", "product_issue"]),
            customer_label=label, submitted_via=req.submitted_via if req else "unknown", subject=subject, body=body)

    @staticmethod
    def _add_usage(usage: Usage, resp) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        usage.input_tokens += getattr(u, "input_tokens", 0) or 0
        usage.output_tokens += getattr(u, "output_tokens", 0) or 0
        usage.cache_read_input_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        usage.cache_creation_input_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0
        served_by = getattr(resp, "model", None)
        if served_by:  # with server-side fallback, the serving model can differ from the requested one
            usage.model = served_by

    @staticmethod
    def _parse_final(resp) -> FinalOutput:
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            return FinalOutput.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            msg = str(exc).splitlines()[0][:300]
            raise ProviderError(f"Live model output failed schema validation: {msg}") from exc

    def _result(self, final: FinalOutput, gate: ToolGate, usage: Usage) -> AgentResult:
        c = final.classification
        try:
            cls = Classification(
                category=c.category, priority=c.priority, justification=c.justification[:500],
                summary=c.summary[:500], mentioned_emails=sorted(set(c.mentioned_emails) | set(gate.mentioned_emails)),
                search_queries=(gate.queries or ["(no knowledge-base search was run)"])[:4],
                risk_flags=list(dict.fromkeys([*c.risk_flags, *gate.security_flags])))
        except ValidationError as exc:
            raise ProviderError(f"Live model classification failed validation: {str(exc).splitlines()[0][:300]}") from exc
        return AgentResult(classification=cls, draft=final.proposal, customer=gate.customer,
                           subscription=gate.subscription, tickets=gate.tickets, passages=gate.passages,
                           security_flags=gate.security_flags, usage=usage)


def _retry_after(exc: "anthropic.APIStatusError") -> float | None:
    try:
        v = exc.response.headers.get("retry-after")
        return float(v) if v else None
    except (AttributeError, ValueError):
        return None
