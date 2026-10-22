# ResolveOps

An AI support-operations agent prototype. It reads a support request, looks up the
**authorized** customer's account through typed tools, retrieves company documentation with
embedding search, and drafts a structured, cited proposal. A human then reviews it: edit,
approve, or reject. Only approved ticket actions are executed, and every one is idempotent.
Every step lands in an audit log.

The default workspace is **Northstar Analytics**, a fictional B2B analytics company. All
customers and people are synthetic.

> Status: **Milestone 1** (vertical slice, demo mode). See `docs/PLAN.md` for the milestones,
> `docs/DECISIONS.md` for design decisions, and `docs/SPEC.md` for the full specification.

## Quick start

Requirements: Docker with Compose. No API keys are needed for demo mode.

```bash
cp .env.example .env        # optional; defaults work without it
docker compose up -d --build   # or: make up
```

Open **http://localhost:8080**. The first start runs migrations and seeds Northstar
automatically. The API is also published on http://localhost:8000 (`/api/docs` for OpenAPI).

| Task | Command |
|---|---|
| Start / rebuild | `make up` (`docker compose up -d --build`) |
| Stop (keep data) | `make down` (`docker compose down`) |
| Re-seed Northstar (wipes workspace data) | `make seed` (`docker compose exec api python -m app.seed --reset`) |
| Full reset (drop the DB volume) | `make reset` (`docker compose down -v && docker compose up -d --build`) |
| Backend tests (real Postgres, in container) | `make test` (`docker compose exec api pytest -q`) |
| Frontend typecheck + build | `make test-web` (`cd frontend && npm ci && npm run typecheck && npm run build`) |
| Browser check (stack must be running) | `cd frontend && npm run e2e` |

The browser check uses `playwright-core` and expects a Playwright Chromium build in the local
cache (`npx playwright install chromium` if you don't have one). It writes screenshots to
`docs/screenshots/`.

## Trying it

- **Visitors** need no login. Each browser gets a private demo sandbox. The three buttons in
  the header run the demo scenarios:
  1. **Access issue**: "We upgraded yesterday, but two employees still can't access the
     reporting feature…" The reply uses account facts (the Starter → Pro upgrade, the 7 users
     still on the Viewer role, the admins' names) and cites the permissions docs.
  2. **Billing clarification**: "charged twice". Lists the account's actual invoices this
     period and asks the customer to confirm which charges they mean.
  3. **Escalate product issue**: Snowflake connector failing with NS-CONN-504. An escalation
     rule and the known-issue doc produce a high-priority engineering ticket on approval.
- **Reset my demo** deletes only your sandbox's rows. Other visitors are unaffected.
- **Reviewer sign-in**: `reviewer@northstar.example` / `northstar-demo` (local demo
  credentials, set in `.env`). Reviewers work on the workspace queue rather than a sandbox
  and can open the reviewer-only admin endpoints.
- **New request** submits as a server-issued synthetic customer session. In demo mode only the
  seeded scenario messages are processed. Anything else is recorded as *not processed*, and
  the app does not pretend a model read it.

## How it works (M1)

```
browser ─► web (nginx + React build) ─/api─► api (FastAPI, Python 3.12) ─► Postgres 17 + pgvector
                                              ├─ workflow.py   explicit state machine
                                              ├─ tools.py      typed, context-scoped tools
                                              ├─ providers/    Simulated (demo) │ Claude (M2)
                                              ├─ retrieval.py  fastembed bge-small, 384-dim
                                              ├─ review.py     edit / approve / reject / retry
                                              └─ adapters/     internal tickets │ GitHub (M4)
```

- **The AI proposes and application code decides.** Workspace and customer ids come from
  server sessions, never from model output. Escalation rules are evaluated in code and override
  the draft. Citations are kept only if the chunk was retrieved for that request. Account
  facts are assembled from tool results.
- **Approval is bound to an exact proposal version plus an action hash.** Editing creates a new
  version and invalidates earlier approvals. Execution uses an idempotency key with UNIQUE
  constraints, so double clicks, concurrent approvals and retries produce one ticket.
- **Demo mode is honest.** Simulated outputs are deterministic fixtures labelled
  "Simulated AI — demo mode". Retrieval, tools, approvals, execution and auditing are all real.

## Mode configuration

`AI_MODE=demo` (default) needs no keys. `AI_MODE=live` is Milestone 2. Until then, selecting
it puts requests into an explicit error state ("ANTHROPIC_API_KEY is not set" or "Live provider is
not implemented yet") rather than silently falling back to simulated output.

## Known limitations (M1)

- Live Claude provider, usage limits/budgets, onboarding, document import/replace UI, stale
  proposal invalidation, second workspace, GitHub adapter, evaluation dataset and dashboard
  are later milestones (see `docs/PLAN.md`).
- Escalation-rule matching is simple keyword/category/plan matching.
- No login rate limiting yet. Session cookies are `Secure` only when `COOKIE_SECURE=true`
  (needed behind HTTPS).
