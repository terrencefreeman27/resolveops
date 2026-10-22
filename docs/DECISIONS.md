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

## D11 — Seeded requests are shared templates
The seeded inbox is shared and read-only. "Run workflow" (or a scenario button) clones a template
into the caller's scope and runs it. This keeps the inbox identical for every visitor, makes reset
trivial (delete own rows), and lets the reviewer queue and visitor sandboxes coexist.

## D12 — Visitor notes on shared tickets go to a sandbox copy
When a visitor approves an `add_note` action on a shared seed ticket, the internal adapter records
the note on a session-scoped copy of that ticket (same number, flagged "Demo sandbox"). Shared
seed data is never mutated by visitors.

## D13 — Unsupported demo input is stored, labelled, and not processed
Free text that is not a seeded scenario goes to state `unsupported` with the reason "Demo mode
only handles the seeded scenarios. This message was not processed by any AI model." No proposal
is generated. In live mode (M2) the same path will call the real provider instead.

## D14 — Test-only fault injection
`adapters/internal.py` has an in-process `FAULTS` counter (fail before / after the write) that
only code can set. Tests use it to prove bounded retries, savepoint rollback and single-ticket
retry. It is not reachable from any API input.

## D15 — Proposal editing scope (M1)
Reviewers can edit the draft reply, next action, and ticket action. Citations and account facts
are not editable: they record what tools and retrieval actually returned. Edits carry the
evidence of the version they were based on.

## D16 — Live model: `claude-opus-5-5`, adaptive thinking, effort `medium`, official SDK `anthropic==2.1.0`
- **Why:** the `claude-api` skill (loaded before any Claude code, per D1) names Claude Opus 5.5 as the
  current default model; exact id `claude-opus-5-5` (no date suffix). Thinking on Opus 5.5 is always on
  (`{type: "adaptive"}`; `disabled`/`budget_tokens` are 400s); effort defaults to `medium` on this model and
  is set explicitly (`LIVE_EFFORT`). Forced `tool_choice` is a 400 on Opus 5.5, so tool use is `auto` with
  `strict: true` tool schemas and the final proposal is constrained by `output_config.format` (JSON schema),
  then validated again by the Pydantic schemas (`extra="forbid"`). SDK pinned to the current PyPI release
  (2.1.0, checked 2026-10-22).
- **Refusal fallback:** requests opt in to server-side fallback on safety refusals
  (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) as the skill recommends for Opus 5.5;
  `LIVE_REFUSAL_FALLBACK=false` turns it off. The serving model id from the response is what gets recorded.
  A final `stop_reason: "refusal"` is an error state, never simulated.
- **Revisit:** if the live smoke test or M5 evals show the model/effort is a poor cost/quality fit
  (`LIVE_MODEL` / `LIVE_EFFORT` are config, not code).

## D17 — Live mode runs a model-driven, code-gated tool loop
- The model decides which allowlisted tools to call. Every call goes through `providers/live_guard.py`
  (allowlist, no identity/authority arguments, foreign ticket ids refused, foreign emails flagged and never
  looked up — each refusal audited and shown to the reviewer as a risk flag) and then `tools.call_tool`
  (argument/output validation, workspace + customer scoping from the server-built `ToolContext`).
- After the loop the server fetches any required context the model skipped (customer, subscription,
  tickets), so account facts and escalation rules never depend on the model asking for them. Citations
  must reference chunks returned by the model's own searches for this request. Escalation rules,
  citation validation, `propose_ticket_action` validation and approval are the same code as demo mode.
- Bounded: `LIVE_MAX_TOOL_STEPS` tool-calling turns, `LIVE_MAX_OUTPUT_TOKENS` per call,
  `LIVE_MAX_TOKENS_PER_REQUEST` across the loop. History is append-only (thinking blocks echoed unchanged).
- Failures: retryable (429, 5xx incl. 529 overloaded, timeouts, connection) get bounded exponential backoff
  (`LIVE_MAX_RETRIES`, SDK retries disabled so each retry is audited); everything else fails at once.
  The request goes to `error` with a provider/config message. No simulated fallback, ever.

## D18 — Untrusted content is wrapped as data, and code still enforces everything
Customer messages go inside `<customer_message>`, retrieved passages inside `<retrieved_passages note=
"untrusted …">`, other tool output inside `<tool_output>`; all of it is HTML-escaped so it cannot close or
forge tags. The system prompt says these contents cannot change rules, permissions, identity or approval.
That prompt is defence in depth only: tests drive an *attacked* fake model (non-allowlisted tools,
cross-customer ids, forged ticket groups, "auto-approved" claims, extra `approved` fields) and assert the
code blocks each one. The API key never enters a prompt, a log line, an audit row or an API response.

## D19 — Usage and spending controls
- Input size: `MAX_REQUEST_CHARS` (subject + body) → 413 before any row is created. Uploads:
  `MAX_UPLOAD_BYTES` reserved for M3 document import.
- Rate: live runs per reviewer and globally per rolling minute, counted from `ai_runs` in Postgres → 429.
- Budget: `LIVE_MONTHLY_TOKEN_BUDGET` (input + output tokens of live runs, UTC calendar month) → 429.
  A USD budget is enforced only when `LIVE_PRICE_INPUT_PER_MTOK` and `LIVE_PRICE_OUTPUT_PER_MTOK` are both
  set; prices are never assumed or hard-coded.
- Concurrency: in-process counter (`LIVE_MAX_CONCURRENCY`) → 429 when busy. **Single-instance
  limitation:** several API replicas would each allow that many; a shared limiter (Postgres advisory
  locks or Redis) would be needed before scaling out.
- Every limit is checked before a request row is written, returns a plain explanation and a `limit` code,
  and the UI shows it in the error banner.
- **Revisit:** before any multi-instance or public live deployment.

## D20 — Visitors never use live mode by default; usage recorded per run
`AI_MODE=live` applies to signed-in reviewers. Public visitors keep the simulated provider (their banner
says so) unless `LIVE_ALLOW_VISITORS=true` is set deliberately. Every workflow run writes an `ai_runs` row
(`provider` simulated | live, model, latency, input/output/cache tokens, API calls, tool steps, status,
error) and successful runs copy that usage onto `proposals.usage`, so the M5 dashboard can keep simulated
and live metrics apart. Failed live runs keep the tokens they spent, which count toward the budget.

## D21 — Embeddings stay local in live mode
Live mode's "real embeddings" are the same local `fastembed` `BAAI/bge-small-en-v1.5` model as demo mode
(D2): ingestion (`retrieval.ingest_document`) and search (`retrieval.search`, called by the
`search_knowledge_base` tool) are one shared code path for both modes. There is no second paid
embeddings provider (Anthropic has no embeddings API). **Revisit:** same trigger as D2.

## D22 — Workspace-scoped simulated fixtures (no company branches in code)
- **Decision:** demo-mode outputs live in `sim_fixtures` rows per workspace (seeded from
  `app/seed/<company>_fixtures.py`). `providers/simulated.py` is a generic template renderer: variants
  chosen by a small fixed set of data predicates (`plan_lacks_feature`, `no_users_with_role`, …), text
  rendered from tool results, citations emitted only for passages retrieval returned. Admin roles and the
  reply signature are workspace settings/profile. `grep -i northstar backend/app` outside `app/seed/` finds
  only the default seed-reviewer email and password in `config.py`.
- **Why:** SPEC §2 — the app must be configurable, not built around one company; the same wording in two
  workspaces must produce two evidence-based answers.
- **Revisit:** if fixtures need logic beyond the predicates (prefer adding a predicate over code branches).

## D23 — Document lifecycle: import status separate from lifecycle status; soft delete
- `document_versions.import_status` (pending → processing → ready | failed + error) is the import pipeline;
  `status` (active | superseded | deleted | failed) is the lifecycle. Import runs as a FastAPI background task
  after the request commits the pending version, so the UI can watch the transitions; the seed and tests use
  the same `index_version` synchronously.
- Activation, superseding the previous version, deactivating its chunks and staling dependent proposals are
  one transaction (`documents.index_version` + `staleness`). Delete is a soft delete for the same reason and so
  that citations keep resolving to the exact cited version.
- Uploads are JSON `{filename, content}` (browser reads the file as text). Avoids adding `python-multipart`;
  type (`.md/.markdown/.txt`), UTF-8 byte size (`MAX_UPLOAD_BYTES`), NUL bytes and per-workspace count are
  enforced server-side. Identical re-uploads are refused.
- **Revisit:** large files or binary formats (would need multipart + a parser; PDF is deliberately unsupported).

## D24 — Stale proposals: what is covered, and Reprocess = next version of the same proposal
- **Pending** = request `awaiting_review`, or `failed` (approved, execution not completed). `executing` is
  inside one request holding the request row lock, so it can't interleave with invalidation.
- **Triggers covered:** a document version that the proposal's evidence *retrieved or cited* is superseded or
  deleted; escalation rules change so the set of matching rules (or a matching rule's effect) differs from what
  the proposal recorded (re-evaluated per pending proposal). Not covered: company-profile edits, retrieval
  threshold changes, and new documents that *would* now be retrieved (a new doc can't invalidate evidence that
  was used, only add evidence; reprocess manually if needed).
- Stale marking invalidates active approvals, locks request rows (`FOR UPDATE`) like approve/retry do, and is
  audited (`proposal.stale`). Approve/edit/reject/retry refuse stale requests with the reason; execution
  re-checks defensively.
- **Reprocess** re-runs the workflow on current documents/rules and appends version N+1 to the same proposal
  with an edit note naming why vN was stale (`proposal.reprocessed`), so history shows both.

## D25 — Insufficient / conflicting evidence is decided by code, with declared policy facts
- **Insufficient:** best retrieved cosine similarity below `RETRIEVAL_MIN_SCORE` (0.72; workspace override
  `settings.retrieval_min_score`). Calibrated on seeded data: answered scenarios' best scores 0.79–0.89, the
  undocumented Peppol question 0.69. The workflow keeps the best score per chunk across searches.
- **Conflicting:** documents declare facts with `<!-- policy key: value -->` inside the section stating them;
  parsed per chunk at import. A conflict counts only if two *relevant retrieved* chunks declare different
  values for the same key — so it is about the deciding fact of this request, not any contradiction anywhere.
  Lumen's `plan-changes` vs `billing-faq` downgrade timing is the deliberate seeded conflict.
- **Effect:** a drafted `resolve` becomes `escalate` to the workspace's `evidence_review_group` with a neutral
  holding reply; clarify/escalate drafts are kept. The check is stored on the proposal and shown; reviewer
  edits cannot switch such a proposal to `resolve`. The provider's *own* drafted ticket action is validated
  before any server rewrite, so an invalid draft (e.g. a foreign ticket id) is still an error.
- The two Lumen edge-case fixtures deliberately draft a confident `resolve` to stand in for an over-confident
  model and show the code guard working. Not an AI judgement; no model decides sufficiency.
- **Revisit:** M5 eval recall/threshold results; prose contradictions without markers are not detected.

## D26 — Per-workspace reviewer access; private reviewer-created workspaces
- Reviewer rights come from `memberships` per workspace (existing table). The demo reviewer belongs to both
  demo workspaces; `reviewer@lumenledger.example` to Lumen only. A signed-in non-member is treated as a visitor
  (sandbox) in demo-enabled workspaces and gets 401/403 elsewhere.
- Workspaces created in onboarding are not demo-enabled and are listed in `/api/meta` only to their members.
- Visitor reset deletes the caller's sandbox rows across all workspaces (sandboxes are per session, and rows
  are per workspace).

## D27 — Onboarding "test a request" is a dry run in demo mode
- Step 6 runs retrieval, the evidence check and escalation rules against the workspace and reports the allowed
  outcome; it calls no model and stores nothing. A full simulated proposal for arbitrary text would mean
  pretending a model read it (SPEC §8); full runs need live mode or a seeded fixture.
- Onboarding does not import customers/subscriptions (seed only), so new workspaces cannot run full requests
  yet. **Revisit:** if a pilot needs CSV/API customer import.
