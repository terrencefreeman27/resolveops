# ResolveOps

An AI support-operations agent prototype. It reads a support request, looks up the
**authorized** customer's account through typed tools, retrieves company documentation with
embedding search, and drafts a structured, cited proposal. A human then reviews it: edit,
approve, or reject. Only approved ticket actions are executed, and every one is idempotent.
Every step lands in an audit log.

Two fictional companies are preloaded as separate workspaces: **Northstar Analytics** (B2B
analytics, the default) and **Lumen Ledger** (B2B invoicing, different plans and policies). All
customers and people are synthetic. Reviewers can create further workspaces through an
onboarding flow and import their own Markdown or plain-text documentation.

> Status: **Milestone 5, the final one** (evaluation, dashboard, polish, documentation). Demo mode is verified
> end to end. **Live mode, the GitHub adapter, the live evaluation and the prompt-only baseline have not been run
> against the real services**, because no API key or GitHub token was available. See the
> [what is simulated or unverified](docs/INTERVIEW_WALKTHROUGH.md#8-what-is-simulated-or-unverified) list.
>
> Docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (diagrams) · [`docs/DECISIONS.md`](docs/DECISIONS.md)
> (design decisions and tradeoffs) · [`eval/RESULTS.md`](eval/RESULTS.md) (evaluation) ·
> [`docs/VERIFICATION.md`](docs/VERIFICATION.md) (SPEC §15 checklist with evidence) ·
> [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) · [`docs/INTERVIEW_WALKTHROUGH.md`](docs/INTERVIEW_WALKTHROUGH.md) ·
> [`docs/SPEC.md`](docs/SPEC.md) · [`docs/PLAN.md`](docs/PLAN.md)

## Quick start

Requirements: Docker with Compose. No API keys are needed for demo mode.

```bash
cp .env.example .env        # optional; defaults work without it
docker compose up -d --build   # or: make up
```

Open **http://localhost:8080**. The first start runs migrations and seeds both demo workspaces
automatically (an existing database gets any missing demo workspace on the next start). The API is also published on http://localhost:8000 (`/api/docs` for OpenAPI).

| Task | Command |
|---|---|
| Start / rebuild | `make up` (`docker compose up -d --build`) |
| Stop (keep data) | `make down` (`docker compose down`) |
| Re-seed the demo workspaces (wipes Northstar + Lumen data; reviewer-created workspaces untouched) | `make seed` (`docker compose exec api python -m app.seed --reset`) |
| Full reset (drop the DB volume) | `make reset` (`docker compose down -v && docker compose up -d --build`) |
| Backend tests (real Postgres, in container) | `make test` (`docker compose exec api pytest -q`) |
| Frontend typecheck + build | `make test-web` (`cd frontend && npm ci && npm run typecheck && npm run build`) |
| Browser checks (stack must be running) | `make e2e` (`cd frontend && npm run e2e`) |
| Evaluation: AI eval (demo), live status, backend checks | `make eval` (see [Evaluation](#evaluation)) |
| Live AI eval + prompt-only baseline (needs a key) | `make eval-live` |

The browser check uses `playwright-core` and expects a Playwright Chromium build in the local
cache (`npx playwright install chromium` if you don't have one). It writes screenshots to
`docs/screenshots/`. Some checks assume freshly seeded data, so run it after `make reset`.

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
- **Dashboard** (header button, or `#dashboard`): requests by category and state, approval outcomes, ticket
  executions, simulated and live AI usage shown separately, and the latest evaluation results labelled by mode.
  Visitors see only their own sandbox. Reviewers see the workspace queue (`docs/DECISIONS.md` D31).
- **Switch company** with the workspace selector under the ResolveOps name. Lumen Ledger's
  inbox contains the *same* access-after-upgrade and "charged twice" wording as Northstar; the
  answers differ because they come from Lumen's account data and documents (see below).
- **Reviewer sign-in**: `reviewer@northstar.example` / `northstar-demo` is a reviewer of both
  demo workspaces. `reviewer@lumenledger.example` / `lumen-demo` is a reviewer of Lumen Ledger
  only (in Northstar they are just a sandboxed visitor). Local demo credentials; the first is
  set in `.env`. Reviewers work on the workspace queue rather than a sandbox.
- **New request** submits as a server-issued synthetic customer session. In demo mode only the
  seeded scenario messages are processed. Anything else is recorded as *not processed*, and
  the app does not pretend a model read it.

## Same request, two companies

| | Northstar Analytics | Lumen Ledger |
|---|---|---|
| "We upgraded yesterday, but two employees still can't access the reporting feature…" | Pro includes Reporting, but the upgrade didn't change roles: 7 users are still Viewers. An Admin should change the two employees to **Analyst**. Cites *Roles and Permissions*, *Troubleshooting Reporting*, *Plans and Features*. | The customer moved Essentials → Growth, and **Growth does not include Insights reporting at all; Scale is required**. Cites *Plans and Pricing* and *Team Roles and Permissions*. |
| "We were charged twice this month…" | **Clarify**: lists the renewal and the *prorated* seat add-on invoice and asks the customer to confirm amounts. | **Resolve**: Lumen doesn't prorate upgrades; the full Growth price was charged on an upgrade invoice and unused Essentials time comes back as **account credit on the next invoice**. |
| Refund for 2 unused seats | Escalates to **Billing**, normal priority. | Escalates to **Accounts Receivable**, high priority (credits only, no card refunds). |

Lumen also seeds the two evidence edge cases: a downgrade question where two current documents
disagree (escalated as *conflicting evidence*) and a Peppol e-invoicing question that no document
covers (escalated as *insufficient evidence*).

## Reviewer onboarding (Workspace setup)

Signed-in reviewers open **Workspace setup** in the header. Visitors see a sign-in prompt, and
the server refuses every setup endpoint for them (403). Reviewer access is per workspace: a
reviewer of workspace A cannot read or change workspace B.

1. **Company details**: create a workspace (name, description, support hours, reply signature,
   allowed ticket groups). The creator becomes its first reviewer. New workspaces are private:
   they are not demo-enabled and are invisible to visitors and to other reviewers.
2. **Import documents**: **Markdown (`.md`, `.markdown`) and plain text (`.txt`) only.** PDF,
   Word, HTML and anything else is rejected with a message saying so. Limits: `MAX_UPLOAD_BYTES`
   (default 200 KB per file) and `MAX_DOCUMENTS_PER_WORKSPACE` (default 40). Markdown is split
   into sections at `##` headings; plain text into paragraph groups.
3. **Review documents**: import status (`pending → processing → ready`, or `failed` with the
   error), every version, and the sections exactly as they are indexed. Replace and Delete live
   here.
4. **Escalation rules**: category, keyword and plan conditions → escalate to an allowed group at
   a priority. Evaluated by code, not by the model.
5. **Ticket adapter**: Internal tickets, or GitHub Issues when the server is configured for it (see
   [Optional GitHub Issues integration](#optional-github-issues-integration)). Otherwise GitHub is
   listed as *Not configured* with the server's reason.
6. **Test a sample request**: a dry run of retrieval, the evidence check and the escalation rules
   against this workspace. It calls no AI model and stores nothing. In demo mode, full proposals
   exist only for the seeded scenarios, which are workspace data (`sim_fixtures`).

### Document lifecycle

- Documents have stable ids. Every import or replacement is a numbered **version**, and each
  version is split into sections (chunks) with embeddings.
- **Replace** activates the new version, marks the old one *superseded* and removes its chunks
  from retrieval. **Delete** is a soft delete: the document leaves retrieval but stays in the
  database, so old citations still resolve.
- Each proposal records which document versions it retrieved and cited. When a version is
  superseded or deleted, every **pending** proposal that used it (awaiting review, or approved
  but execution failed) is marked **stale** in the same database transaction. Approve, edit and
  retry are refused for stale proposals. **Reprocess** re-runs the workflow against current
  documents and adds a new version of the same proposal. Both events are audited.
- Changing escalation rules re-checks pending proposals, and those whose matching rules changed
  are marked stale the same way.
- Citations always open the exact version they cite, labelled "superseded by vN" or "deleted"
  when that version is no longer current.

### Insufficient or conflicting evidence

Application code checks every proposal's retrieved passages (`app/evidence.py`):
- **Insufficient**: no passage reaches the relevance threshold (`RETRIEVAL_MIN_SCORE`, default
  0.72 cosine similarity, which can be overridden per workspace).
- **Conflicting**: two relevant passages from current documents state different values for the
  same policy key. Documents declare such facts inside the section that states them:
  `<!-- policy plan_change.downgrade_effective: end of term -->`.

In either case a drafted "resolve" becomes an escalation with a holding reply, and a reviewer edit
cannot turn it back into a resolve. The UI shows the check, the disagreeing passages and what was
changed.

## How it works

Diagrams (containers, state machine, request path, tool gate, evidence and staleness checks):
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
browser ─► web (nginx + React build) ─/api─► api (FastAPI, Python 3.12) ─► Postgres 17 + pgvector
                                              ├─ workflow.py   explicit state machine
                                              ├─ tools.py      typed, context-scoped tools
                                              ├─ providers/    Simulated (demo) │ Claude live (M2)
                                              ├─ retrieval.py  fastembed bge-small, 384-dim
                                              ├─ review.py     edit / approve / reject / retry
                                              └─ adapters/     internal tickets │ GitHub Issues
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

`AI_MODE=demo` (default) needs no keys: every caller gets deterministic simulated AI.

### Live mode (Milestone 2) — enable deliberately

Live mode sends **signed-in reviewers'** requests to Claude (`claude-haiku-5-5` by default, official
`anthropic` SDK). The key is read only by the `api` container, only from `./.env` (never from your shell
environment), and is excluded from Git and from both Docker build contexts. Public visitors stay on simulated AI unless `LIVE_ALLOW_VISITORS=true`. Do not enable it on a
public deployment without reviewing the limits below.

1. Put these lines in `.env` (gitignored; never commit a key):
   ```
   AI_MODE=live
   ANTHROPIC_API_KEY=<your key>
   # optional, defaults shown
   LIVE_MODEL=claude-haiku-5-5   # no server-side refusal fallback on Haiku 5.5; refusals end in the error state
   LIVE_EFFORT=medium
   LIVE_MONTHLY_TOKEN_BUDGET=2000000
   LIVE_RATE_PER_REVIEWER_PER_MIN=5
   LIVE_RATE_GLOBAL_PER_MIN=20
   LIVE_MAX_CONCURRENCY=2
   LIVE_MAX_TOOL_STEPS=6
   LIVE_MAX_OUTPUT_TOKENS=8000
   # USD budget is enforced only if BOTH prices are set (no prices are assumed). Haiku 5.5 list price,
   # checked 2026-10-23, for prompts up to 100K tokens (higher above 100K):
   LIVE_PRICE_INPUT_PER_MTOK=0.10
   LIVE_PRICE_OUTPUT_PER_MTOK=0.50
   LIVE_MONTHLY_USD_BUDGET=5
   ```
2. `docker compose up -d --force-recreate api`
3. Sign in as the reviewer, open **AI status** (mode, model, key configured yes/no, budget, limits),
   then run a scenario or submit a new request.
4. Optional live smoke test (spends real tokens): `docker compose exec api pytest -m live -q`

Without a key, live requests go to an `error` state with "Live mode: ANTHROPIC_API_KEY not
configured" and the banner turns red. A failed live call is never replaced by simulated output.
Limits (size, rate, budget, concurrency) return 413/429 with an explanation; nothing is created.
Each proposal shows which provider produced it and, for live runs, model, tokens, tool calls and
latency. Details: `docs/DECISIONS.md` D16–D21.

## Optional GitHub Issues integration

> **Unverified against real GitHub.** The adapter is tested only against a fake HTTP transport
> (`backend/tests/test_github_adapter.py`). The `github_live` smoke test exists but has not been run.

When enabled, approving an **escalation** in a reviewer workspace that selected *GitHub Issues*
creates one issue in a single, server-configured test repository. Everything else stays internal:
non-escalation tickets, notes, and every visitor sandbox (enforced server-side). The base URL is
fixed to `https://api.github.com`; the repository comes only from server config and must also be
on the allowlist. Nothing in a proposal can choose the host, URL or repository.

**What goes into the issue** (built by code, Markdown-escaped, `@mentions` neutralised, length-limited):
title `[ResolveOps] <approved ticket subject>`; workspace name; category, priority, group; the
customer's company name and account reference labelled *synthetic test customer*; the approved ticket
body; the request id; and a hidden marker `<!-- resolveops-execution: <idempotency key> -->`.
**Not included:** customer emails, the customer's original message, the draft reply, reviewer
identity, retrieved passages or scores. Optional labels come from `GITHUB_LABELS`.

**Enable it (test repository only):**
1. Create a dedicated, empty test repository on GitHub (e.g. `<you>/resolveops-test`), private is fine.
   Do not use a real project repository.
2. Create a **fine-grained personal access token**: *Settings → Developer settings → Fine-grained
   tokens → Generate*. Resource owner: you. Repository access: **Only select repositories** → that
   one test repository. Repository permissions: **Issues: Read and write** (Metadata: read-only is
   added automatically). No other permissions. Set a short expiry.
3. Add to `.env` (gitignored; never commit the token):
   ```
   GITHUB_ADAPTER_ENABLED=true
   GITHUB_TOKEN=<fine-grained token>
   GITHUB_ISSUES_REPO=<owner>/<test-repo>
   GITHUB_ALLOWED_REPOS=<owner>/<test-repo>
   # optional (labels need push access, otherwise GitHub silently drops them)
   # GITHUB_LABELS=resolveops,synthetic-test
   # GITHUB_TIMEOUT_S=10
   # GITHUB_MAX_ATTEMPTS=3
   # GITHUB_RETRY_BASE_DELAY_S=1
   # GITHUB_MAX_WAIT_S=10
   ```
4. `docker compose up -d --force-recreate api`
5. Sign in as the reviewer. **AI status** shows *GitHub Issues configured: Yes* and the destination
   repository (never the token). In **Workspace setup → step 5** select *GitHub Issues*.
6. Run the *connector outage* scenario and approve it: the ticket card and action history link to the
   new issue.
7. Optional smoke test (creates **one** real, clearly labelled issue in the test repo, then checks
   that a retry with the same execution key finds it instead of creating a second):
   `docker compose exec api pytest -m github_live -q`

**Failures and duplicates.** Before creating, and before every re-send after a timeout, network
error or 5xx, the adapter lists the repository's recently updated issues and reuses one carrying this
execution's marker, so a lost response, a double approval or a retry does not create a second issue.
5xx and rate limits are retried a bounded number of times (honouring `Retry-After` /
`x-ratelimit-reset`; waits longer than `GITHUB_MAX_WAIT_S` fail with the wait time instead of
blocking). 401/403/404/410/422 fail at once with a recorded error. A failed GitHub execution offers
**Retry** and an explicit **Use internal ticket instead** action, which is refused if GitHub already
has an issue for that execution. Details and limits: `docs/DECISIONS.md` D28–D30.

## Evaluation

The full write-up, with every number and caveat, is in [`eval/RESULTS.md`](eval/RESULTS.md). The dataset datasheet
is [`eval/datasets/v1/README.md`](eval/datasets/v1/README.md). The stack must be running.

```bash
make eval
# = docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode demo
#   docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode live
#   docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_backend_eval
```

Each run writes `eval/results/<suite>-<mode>-<date>.json`, and the dashboard shows the latest file per suite and mode.
Results at commit `d6b8d5c` (2026-10-22):

- **AI task eval, demo mode: Simulated, not evidence of AI performance.** Of 50 cases, 30 were evaluated,
  5 were refused at the gate and 15 are unsupported in demo mode (no fixture; excluded from rates). Correct next
  action 32/35. Clarify-when-expected 2/5: three honest fixture failures. Citations valid 67/67. Must-not
  violations 0. Execution steps (double, concurrent and lost-response approvals, stale refusal) 7/7. A
  raw-message retrieval probe found the 0.72 evidence threshold too strict for unfocused queries.
- **AI task eval, live mode: not run** (no `ANTHROPIC_API_KEY`). The prompt-only baseline is also **not run**.
  Command: `make eval-live`.
- **Deterministic backend checks: 64/64 passed** across 10 categories (authorization, isolation, unauthorized
  actions, approval versioning, stale evidence, evidence guard, duplicates, injection, failures without fallback).

## Known limitations

What is **simulated or unverified** (details: [`docs/INTERVIEW_WALKTHROUGH.md`](docs/INTERVIEW_WALKTHROUGH.md#8-what-is-simulated-or-unverified)):
- **Live Claude** has never been called. The live provider is tested only with a scripted fake client, and the
  `pytest -m live` smoke test has not been run.
- **GitHub Issues** has been tested only against a fake HTTP transport. The `github_live` smoke test has not been run.
- **Live evaluation and the prompt-only baseline** have not been run. **No LLM judge** exists. Citation-support
  labels and all dataset labels were written by the build agent and **have not been reviewed by a human**.
- **Demo mode** answers only the seeded wordings, from fixtures. It cannot show how a model handles new text.

Product and engineering limits:
- The live concurrency limit is held in memory per API process (single-instance deployment assumed). Rate limits
  and the budget count live runs in the database, but the check-then-run is not protected by a distributed lock.
- Execution is synchronous inside the approve request. There is no job queue or background worker, so a slow
  adapter holds the HTTP request (bounded by attempt timeouts).
- The evidence threshold (0.72) was calibrated on fixture queries. Raw customer wording often scores lower and
  would be escalated (see `eval/RESULTS.md`). Conflict detection only sees facts that documents declare with
  policy markers; it does not infer contradictions from prose.
- Stale invalidation covers document versions a proposal *retrieved or cited*, and rule changes. Changes to
  company details or ticket groups do not stale proposals (removing a ticket group that escalation rules still
  route to is refused).
- Onboarding imports documents, rules and company details, but not customers or subscriptions. A new
  workspace can therefore dry-run retrieval and rules but cannot run full requests. Documents are uploaded as
  text in a JSON body (no multipart parser).
- Escalation-rule matching is simple keyword, category and plan matching. GitHub issues are not updated after
  creation. Draft replies are never sent: there is no email or chat channel.
- There is no login rate limiting. Session cookies are `Secure` only when `COOKIE_SECURE=true` (needed behind HTTPS).

### What a real pilot would still require

1. **A real identity provider** (SSO/OIDC) for reviewers and customers, instead of local demo passwords and
   synthetic customer sessions; role-based reviewer permissions; login rate limiting.
2. **Live model evaluation on real (consented, de-identified) tickets**, with human-reviewed labels and a second
   labeller for agreement. Re-calibrate the evidence threshold on live query logs. Run the prompt-only baseline,
   and decide whether to add an LLM judge (itself validated against human judgements).
3. **A real ticketing system integration** (Zendesk, ServiceNow, Jira and so on), verified end to end, with
   webhooks for status sync. Update existing issues, not only create them.
4. **Multi-instance operation**: shared rate limiting and concurrency (e.g. Redis), a durable job queue for
   execution with retries outside the request path, and health and alerting.
5. **PII handling**: data classification, redaction before prompts and logs, retention and deletion policies,
   access audit export, a data-processing agreement with the model provider, and region constraints.
6. **Operational controls**: monitoring of live cost against budget, prompt and version management, and an
   incident runbook for provider outages, which already fail closed into the `error` state.
