# Decisions

Short records: decision, why, revisit when.

## D1 — LLM provider: Anthropic Claude (live mode only)
- **Why:** one provider per spec; strong tool use + structured output. Demo mode never calls it.
- **Rule:** the `claude-api` skill must be loaded before any Claude code is written (M2) so model ids,
  SDK version and parameters come from current docs, not memory.
- **Revisit:** if structured output/tool use proves unreliable for the proposal schema.

## D2 — Embeddings: local `fastembed` + `BAAI/bge-small-en-v1.5` (384-dim)
- **Why:** Anthropic has no embeddings API. A local ONNX model gives *real* semantic retrieval in
  both demo and live mode with no paid key, no network at runtime (model baked into the image),
  and no extra service. Verified: `fastembed==0.9.0` installs and embeds on `python:3.12-slim`
  (linux/arm64 under Colima), 384-dim output.
- **Consequence:** M1 already uses real embeddings; no placeholder to replace in M2.
- **Revisit:** if retrieval recall in the M5 eval is poor (try bge-base 768-dim or a hosted model).

## D3 — Backend stack (pinned)
Python 3.12, FastAPI 0.158.2, uvicorn 0.54.0, SQLAlchemy 2.1.6, Alembic 1.20.0, psycopg 3.3.6,
pydantic 2.14.1, pydantic-settings 2.16.1, pgvector 0.5.1 (python), fastembed 0.9.0,
argon2-cffi 25.1.0, pytest 9.1.1, httpx 0.28.1. Versions checked on PyPI 2026-10-21.
Plain SQLAlchemy (not SQLModel) to keep ORM models and API/tool schemas separate.

## D4 — Frontend stack (pinned)
React 19.3.1, Vite 8.3.5, @vitejs/plugin-react 6.1.2, Tailwind 4.3.3 (`@tailwindcss/vite`),
TypeScript **5.9.3** (not 7.x: TS 7 is the native-compiler rewrite; 5.9 is the proven pairing with
Vite 8 in the sibling project). No data-fetching or UI libraries; `fetch` + small hooks.
Served by `nginx:alpine` which proxies `/api` to the API container.

## D5 — Request lifecycle: outcome is a property of the approved proposal
The brief lists `approved/rejected/needs_clarification/escalated` side by side. Clarification and
escalation are what a reviewer approves, so they are modelled as the proposal's `next_action`
(`resolve`/`clarify`/`escalate`) and recorded as the request's `resolution` after execution.
State stays a short linear machine (see PLAN §4) and every approval goes through the same
execution path. `unsupported` and `error` are explicit terminal states.

## D6 — Visitor demo sessions are copy-on-write sandboxes
Seeded requests are templates; running one clones it into the visitor's session. Visitors may
approve inside their sandbox (it exercises the real approval/execution code against the internal
adapter with session-tagged rows) — otherwise the "approval creates a ticket" demo would require
registration, which the spec forbids. Approval of non-sandbox (workspace) requests, document
import, settings and external adapters require reviewer login.

## D7 — Synchronous workflow
The pipeline runs inside the HTTP request. Simulated mode completes in well under a second plus
embedding time. Keeps the critical path inspectable. **Revisit:** if live latency makes the UI
feel blocked (move `run_request` to a background task; the function is already self-contained).

## D8 — Idempotency
`idempotency_key = sha256(proposal_version_id + ":" + action_hash)`; UNIQUE on `executions` and on
`tickets`. Approve/execute takes `SELECT … FOR UPDATE` on the request row. A retry re-uses the
same execution row and key, so a ticket created by a "failed-after-write" attempt is found, not
duplicated. Retries are bounded (3 attempts, per-attempt timeout).

## D9 — Simulated provider depends on real retrieval
Simulated outputs are fixtures keyed by seeded scenario text, but citations must still be among
the chunks actually retrieved by pgvector for that request, and account facts come from tools.
If retrieval does not return the expected passage the proposal fails citation validation rather
than citing something unretrieved.

## D10 — CSRF guard
Cookie auth + `SameSite=Lax` + required `X-ResolveOps: 1` header on mutating requests (browsers
cannot send custom headers cross-site without CORS preflight, and no CORS is enabled).
