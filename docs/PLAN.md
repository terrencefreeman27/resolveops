# ResolveOps — Implementation Plan

Source of truth: `docs/SPEC.md`. Decisions and deviations: `docs/DECISIONS.md`.

## 1. Shape of the system

```
browser ──► web (nginx, static React build) ──/api──► api (FastAPI, Python 3.12)
                                                        │  workflow engine (state machine)
                                                        │  tools (typed, context-scoped)
                                                        │  AI provider: Simulated | Live (Claude)
                                                        │  embeddings: fastembed bge-small (local ONNX)
                                                        │  ticket adapter: Internal | GitHub (M4)
                                                        ▼
                                                      db (Postgres 17 + pgvector)
```

One backend process, one database, one static frontend. No queues, no microservices,
no agent framework. The workflow runs synchronously inside a request (fast enough for
demo and for a single live model call per step); it is written so a worker could
call the same function later.

## 2. Backend layout (`backend/app/`)

| Module | Responsibility |
|---|---|
| `config.py` | Settings from env (pydantic-settings). Mode `demo`/`live`. |
| `db.py` | Engine, session factory. |
| `models.py` | SQLAlchemy 2 models (all workspace-scoped). |
| `schemas.py` | Pydantic v2 models: tool I/O, proposal, API DTOs. |
| `security.py` | Password hashing (argon2), session tokens, CSRF header check. |
| `context.py` | `Actor` / `ToolContext` resolution from cookies — the only source of authorization facts. |
| `tools.py` | `lookup_customer`, `get_subscription`, `search_knowledge_base`, `get_existing_tickets`, `propose_ticket_action`. Allowlisted registry, validated args/outputs, audited with timing. |
| `retrieval.py` | Chunking (by Markdown section), embedding (fastembed), pgvector search over *active* chunks only. |
| `providers/` | `base.py` interface; `simulated.py` deterministic fixtures; `live.py` (M2, Claude). |
| `rules.py` | Deterministic escalation-rule evaluation (application code, not the model). |
| `workflow.py` | The explicit state machine + pipeline `run_request()`. |
| `review.py` | Edit / approve / reject / retry; approval binding; execution with idempotency. |
| `adapters/` | `base.py` `TicketAdapter`; `internal.py`; `github.py` (M4). |
| `audit.py` | Append-only audit writer. |
| `seed/` | Northstar Analytics data + Markdown docs; scenario fixtures. |
| `api/` | Routers: auth, demo, requests, review, knowledge, tickets, meta. |

## 3. Data model (every business table carries `workspace_id`)

- `workspaces` (slug, name, profile jsonb, settings jsonb: adapter, demo_enabled)
- `reviewers`, `memberships` (reviewer ↔ workspace, role), `auth_sessions` (hashed token, expiry)
- `demo_sessions` (hashed token, workspace-agnostic, last_seen)
- `customer_sessions` (hashed token, workspace_id, customer_id, demo_session_id) — server-issued synthetic customer identity
- `customers` (synthetic flag, company, contact email, metadata) and `account_users` (the customer's employees: role → permissions)
- `subscriptions` (plan, status, seats purchased/used, period dates, previous plan, changed_at, features)
- `invoices` (number, kind: renewal/proration/seat_addon, amount, issued_at, status)
- `documents` → `document_versions` (version, content hash, status processing/active/superseded/deleted/failed) → `chunks` (section, ordinal, text, `embedding vector(384)`, `active`)
- `escalation_rules` (category/keywords/plan conditions → target group, priority, human_only)
- `support_requests` (state, category, priority, resolution, scenario_key, `customer_id` = authorized customer, `demo_session_id`, `is_template`, `source_request_id`)
- `proposals` (one per workflow run of a request; `current_version`) → `proposal_versions` (content jsonb, `action_hash`, author, `valid`) → `proposal_evidence` (version ↔ document_version ↔ chunk)
- `approvals` (proposal_version_id, action_hash, decision, actor, status active/invalidated; partial unique index: one active approval per proposal)
- `executions` (`idempotency_key` UNIQUE = sha256(proposal_version_id:action_hash), status, attempts, last_error, ticket_id)
- `tickets` (number, status, priority, group, `idempotency_key` UNIQUE, external_id/url for M4, notes jsonb, `demo_session_id`)
- `audit_log` (actor, event, tool_name, summary jsonb, duration_ms, error, request_id, demo_session_id)

### Visitor isolation (copy-on-write)
Seeded inbox requests are **templates** (`is_template=true`, `demo_session_id NULL`). Running one
clones it into the caller's scope: visitors → rows tagged with their `demo_session_id`;
reviewers → workspace scope (`demo_session_id NULL`). Every query filters by
`(workspace_id, scope)`. "Reset my demo" deletes only rows with the caller's
`demo_session_id`. Seeded tickets/customers/docs are shared read-only reference data.

## 4. Request state machine (`workflow.py`, one table of allowed transitions)

```
received → classified → context_resolved → retrieved → awaiting_review
                    ↘ unsupported (demo input not a seeded scenario / unsupported category / no authorized customer)
awaiting_review → awaiting_review   (edit: new proposal version, prior approval invalidated)
awaiting_review → approved → executing → completed | failed
awaiting_review → rejected
awaiting_review → stale              (M3: cited document version superseded/deleted)
failed → executing                   (retry, same idempotency key)
stale | rejected | error → received  (explicit reprocess = new proposal)
any pipeline step → error            (provider/tool failure recorded; never silently replaced)
```
The proposal's `next_action` (`resolve` | `clarify` | `escalate`) decides the
`resolution` recorded on completion (`resolved`, `awaiting_customer`, `escalated`), so
"needs clarification" and "escalated" are outcomes of an approved proposal rather than
separate execution paths.

## 5. Tool layer
`ToolContext(workspace_id, customer_id, demo_session_id, actor)` is built by the server and
passed to every tool; tools never accept workspace/customer ids from model output.
`lookup_customer(email?)` only returns the authorized customer and reports
`mismatch` when a different email is mentioned. Every tool call writes an audit row with
args summary, result summary, duration and error. `propose_ticket_action` is pure: it
validates and returns a proposed action; it cannot write tickets.

## 6. Provider interface
```python
class AIProvider(Protocol):
    label: str                      # "Simulated AI — demo mode" | "Claude (live)"
    def classify(req) -> Classification
    def plan_lookups(req, cls) -> MissingInfo        # what the request still needs
    def synthesize(req, facts, passages, rules) -> ProposalDraft
```
Simulated: deterministic fixtures keyed by the seeded scenario text; unknown text →
`UnsupportedInDemo` (request marked `unsupported` with an explicit message).
Live (M2): Claude via the official SDK with tool use and structured output.
**Before writing any Claude code, load the `claude-api` skill** and confirm model ids /
SDK version from current docs. A failed live call → `error` state, never simulated fallback.

## 7. Ticket adapter interface
```python
class TicketAdapter(Protocol):
    name: str
    def create_ticket(ctx, action, idempotency_key) -> TicketResult
    def add_note(ctx, ticket_id, note, idempotency_key) -> TicketResult
```
Internal adapter writes `tickets` rows (unique idempotency key). GitHub adapter (M4)
creates issues in one allowlisted repo, stores issue id/url, looks up by idempotency
marker before creating.

## 8. Auth model
- Reviewer: email + password (argon2), opaque session cookie (hashed in DB), memberships per workspace.
- Visitor: anonymous demo session cookie created on first visit; may run seeded scenarios and
  approve **inside their own sandbox only** (internal adapter, session-tagged rows).
  Cannot import docs, change settings, view credentials, submit live-model requests or use external adapters.
- Synthetic customer: server-issued customer session bound to one customer id; submitted
  requests take `customer_id` from the session, never from the body.
- Mutating requests require `X-ResolveOps: 1` header (CSRF guard) + SameSite=Lax cookies.

## 9. API surface (M1)
```
GET  /api/health, /api/meta
POST /api/auth/login | /api/auth/logout      GET /api/auth/me
POST /api/demo/session | /api/demo/reset
GET  /api/w/{ws}/requests?state=&category=   GET /api/w/{ws}/requests/{id}
POST /api/w/{ws}/scenarios/{key}/run         POST /api/w/{ws}/requests   (free text)
POST /api/w/{ws}/requests/{id}/run           (reprocess)
PUT  /api/w/{ws}/requests/{id}/proposal      (edit → new version)
POST /api/w/{ws}/requests/{id}/approve | /reject | /retry
GET  /api/w/{ws}/requests/{id}/audit         GET /api/w/{ws}/chunks/{chunk_id}
GET  /api/w/{ws}/tickets                     GET /api/w/{ws}/customers (reviewer)
POST /api/w/{ws}/customer-session            (issue synthetic customer session)
```

## 10. Milestones
1. **Vertical slice (this run).** Compose stack, migrations, Northstar seed, real local
   embeddings + pgvector retrieval, tools, simulated provider, state machine, proposal
   validation + citations, edit/approve/reject/retry, internal tickets with idempotency,
   audit log, reviewer login, visitor sessions + reset, support-workspace UI, pytest suite,
   tsc + build, browser check.
2. **Live retrieval + model.** Load `claude-api` skill; `providers/live.py` with Claude tool
   use + structured output, same tools/validation; live config errors surfaced; rate limit,
   token/output caps, usage budget, concurrency limit; live disabled for visitors.
3. **Configurable workspaces + doc lifecycle.** Onboarding flow (create workspace, import
   .md/.txt, review import status, escalation rules, adapter choice, test request);
   replace/delete docs → deactivate chunks → mark dependent pending proposals `stale` and
   block their execution; reprocess path; second company with different policies.
4. **GitHub Issues adapter.** Env-configured token + single allowlisted repo; idempotent;
   failures recorded; labelled unverified if no credentials.
5. **Evaluation + polish + docs.** 50-case versioned dataset; deterministic vs AI evals;
   baseline comparison; dashboard (by category/state, approvals, failures, latency/tokens,
   eval results; simulated vs live separated); README, architecture diagram, interview
   walkthrough, demo script.
