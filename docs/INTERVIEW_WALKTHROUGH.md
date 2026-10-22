# ResolveOps: interview walkthrough

A guide to explaining the system out loud. Paths are relative to `backend/app/` unless noted.

## 1. The business problem

B2B SaaS support teams answer the same kinds of tickets all day: "my users can't see feature X after we
upgraded", "why were we charged twice", "the connector is failing". The answer usually depends on two things the
agent has to look up: **this customer's account** (plan, roles, invoices, connectors, open tickets) and **the
company's current policy documents**. Doing that by hand is slow, and getting it wrong is costly: you might promise
a refund, leak another customer's data, or quote a policy that changed last week.

ResolveOps drafts the answer *with the evidence attached*. A human approves it, and only then does anything
happen (a ticket is created or updated). The AI saves the lookup and drafting work. Ordinary code keeps it safe.

## 2. One request, intake to completed ticket

Scenario: Brightline Logistics says two employees can't open Reporting after upgrading.

1. **Intake.** The visitor clicks *Access issue* (`frontend/src/App.tsx` → `api.runScenario`). The server copies
   the seeded request into the visitor's sandbox: `api/requests.py:run_scenario` → `_clone`. A typed request goes
   through `api/requests.py:submit`, which takes the customer **from the server-issued customer session**, never
   from the message.
2. **Live or simulated?** `api/requests.py:_ai_gate` → `providers.live_for(is_reviewer)`. Visitors always get
   simulated AI. Reviewers get live only when `AI_MODE=live`. In live mode, `limits.check_input`,
   `limits.preflight` (rate and budget) and `limits.live_slot` (concurrency) run before any row is written.
3. **Workflow.** `workflow.run_request` records an `AiRun`, picks the provider (`providers.get_provider`), and
   runs `_run_stepwise` (demo) or `_run_agentic` (live):
   - classify → `transition(…, "classified")`;
   - tools through `tools.call_tool`: `lookup_customer`, `get_subscription`, `get_existing_tickets`, all scoped by
     the `ToolContext` built in `workflow.tool_context` from the request row;
   - retrieval: `search_knowledge_base` → `retrieval.search` (pgvector cosine over this workspace's active chunks);
   - `rules.evaluate` (escalation rules, in code);
   - the provider drafts (`synthesize` / the final structured output).
4. **Server-side assembly.** Still in `run_request`: `validate_citations` keeps only chunks retrieved for this
   request. `account_facts` builds the fact panel from tool output. `propose_ticket_action` validates the draft
   action. `evidence.assess` and `evidence.apply` downgrade a confident answer when evidence is insufficient or
   conflicting. A resolve with no citations becomes an escalation. `apply_rules` lets escalation rules override the
   model, and the final action is validated again. `save_version` stores proposal v1 plus a `ProposalEvidence` row
   for every retrieved chunk. State becomes `awaiting_review`.
5. **Review.** The reviewer (or the visitor, inside their own sandbox) reads the proposal, account facts and
   citations. An edit (`review.edit`) creates v2 and invalidates earlier approvals.
6. **Approve.** `review.approve` locks the request row, refuses if the proposal is stale
   (`_refuse_if_stale`), checks the **exact version id and action hash**, inserts the approval (a UNIQUE constraint
   allows one active approval), records an `Execution` with an idempotency key derived from the version, and
   commits *before* any side effect.
7. **Execute.** `review._run_execution` runs each attempt in a savepoint, with bounded attempts and a statement
   timeout. It calls `adapters/internal.py:InternalTicketAdapter.create_ticket` (or `adapters/github.py` for
   escalations in a GitHub workspace). The adapter first looks up the idempotency key, and the `tickets.idempotency_key`
   UNIQUE constraint is the last line of defence. The request becomes `completed` and the ticket is recorded.
8. **Audit.** Every step above calls `audit.record`. The UI timeline (`frontend/src/components/Timeline.tsx`)
   shows the audit rows, including tool names, results, timings and errors.

## 3. How retrieval and tool calling work

- **Ingestion** (`documents.py:create_document` / `create_replacement` → `process_version` → `index_version`):
  Markdown is split at `##` headings and plain text at paragraph groups (`retrieval.split_sections`). Each section
  is embedded locally with bge-small (384-dim) and stored as a `Chunk` tied to an exact `DocumentVersion`.
  Policy markers (`<!-- policy key: value -->`) become `policy_facts` for conflict detection.
- **Search** (`retrieval.search`): embed the query, cosine-rank the active chunks *of this workspace*, return the
  top_k (6) with scores.
- **Tool calling, demo**: the server calls the tools in a fixed order, and the simulated provider renders a
  fixture from their results. **Live**: `providers/live.py:LiveProvider.run_agent` gives Claude the tool
  definitions (`live_prompt.py`). Claude decides which tools to call and with what queries. Each call goes through
  `providers/live_guard.py:ToolGate.run` and then `tools.call_tool`. The loop is capped by `LIVE_MAX_TOOL_STEPS`
  and by the per-request token cap. The final answer must match a JSON schema and is re-validated with Pydantic.
  Required context the model skipped (customer, subscription, tickets) is fetched by the server anyway, so the
  fact panel and rules never depend on the model asking.

## 4. Where ordinary code enforces permissions

| Concern | Where |
|---|---|
| Who is calling, in which workspace | `context.py:actor_for_workspace` (reviewer membership, or demo session in a demo-enabled workspace; otherwise 401), `context.py:require_reviewer` |
| Row scoping (sandbox vs workspace queue) | `context.py:scope_clause`, `api/serializers.py:visible_requests_clause`, `api/requests.py:_get_visible` / `_get_owned` (seeded templates are read-only) |
| Customer identity | `api/requests.py:submit` (session customer; reviewer-selected id must belong to this workspace), `api/session.py:customer_session` |
| Tools stay on the authorized customer | `tools.py:_require_customer` (workspace + customer filter), `tools.py:lookup_customer` (foreign emails are not looked up), `tools.py:propose_ticket_action` (allowed groups; notes only on own tickets) |
| Model tool calls | `providers/live_guard.py:ToolGate.run` (allowlist, refuses `AUTHORITY_KEYS` such as `customer_id`, own tickets only) |
| What the proposal may contain | `workflow.py:validate_citations`, `account_facts`, `apply_rules`; `evidence.py:assess` / `apply` |
| Approval and execution | `review.py:approve` / `edit` / `retry` / `_refuse_if_stale`, `review.py:_adapter_name` (visitors are always internal) |
| Stale evidence | `staleness.py:invalidate_for_document_versions`, `invalidate_for_rule_change`, `mark_stale` |
| Admin actions (documents, rules, adapters) | `api/admin.py` (every route `require_reviewer`; `_own_doc` scopes documents to the workspace) |
| Live usage | `providers.live_for` (visitors never live), `limits.py:check_input` / `preflight` / `live_slot` |
| External destination | `adapters/github.py` (fixed base URL; repo must be configured *and* allowlisted) |
| CSRF | `main.py:csrf_guard` (mutations need the `X-ResolveOps` header) |

The model never supplies identity, scope, permissions or destinations. It can only *ask* for tools, and the gate and
tools decide.

## 5. Why approval is required

- The model can be wrong or manipulated (prompt injection in a message or a document). The approval step puts a
  human between any model output and any side effect.
- Approval binds to **one exact version and an action hash** (`schemas.action_hash` covers next action, reply and
  ticket action). Edits invalidate it, and so does stale evidence. "Approve whatever is current" is impossible.
- Some outcomes are human-only by policy (refunds, security). Escalation rules force those into tickets for the
  right team, whatever the draft says.

## 6. Failures and duplicates

- **Provider failure** (missing key, 401/403/404/400, retries exhausted, refusal, schema-invalid output, token cap):
  `ProviderError` → request `error`, the `AiRun` is marked error, and **no simulated fallback**. Retryable errors
  (429, 5xx, 529, timeouts) get bounded exponential backoff in `LiveProvider._call`.
- **Ticket system failure**: each attempt runs in a savepoint (no partial rows). After `EXECUTION_MAX_ATTEMPTS` the
  request is `failed`, with the error in the timeline. **Retry** reuses the same execution and idempotency key. Editing
  after a failure requires a new approval.
- **Duplicates**: one active approval per proposal (UNIQUE). One execution per version (UNIQUE idempotency key).
  The adapter looks up the key before writing, and the tickets table has a UNIQUE key. GitHub uses a hidden marker
  plus a lookup before every (re)send. Double clicks, concurrent approvals, lost responses and retries all produce
  exactly one ticket (tests in `backend/tests/test_duplicates.py`, `test_approval.py`, `test_github_adapter.py`).

## 7. What the evaluation measures, and what it doesn't

- **Measures** (`eval/RESULTS.md`): over 50 labelled synthetic cases, classification accuracy, correct next action,
  retrieval recall against labelled sections, citation validity (exists, retrieved, current), clarify and escalate
  rates, escalation routing, must-not constraints (no execution without approval, no cross-customer identifiers,
  no refund promises, no simulated fallback, no duplicate or stale execution), and execution scenarios. A raw-message
  retrieval probe covers every message case without a model. A separate deterministic suite of 64 backend tests
  gives real pass/fail numbers for authorization, approval and execution guarantees.
- **Doesn't measure**: how a real model performs. The demo numbers come from fixtures and are labelled "Simulated —
  not evidence of AI performance", and 15/50 cases are not covered at all in demo mode. Live results do not exist
  yet. Citation *support* is judged only by agent-written labels on citation claims, not on every sentence of a reply.
  Dataset labels come from one labeller (the build agent) and have no human review. The string-based leak check
  would miss a paraphrased leak. There is no user-facing quality or satisfaction measure, and no business impact
  is estimated.

## 8. What is simulated or unverified

| Feature | Status |
|---|---|
| Demo-mode AI | **Simulated.** Deterministic fixtures for the seeded wordings only. Retrieval, tools, rules, evidence checks, approval, execution and audit are real. |
| Live Claude provider | **Built, never called.** Tested with a scripted fake SDK client (`tests/live_fakes.py`). `pytest -m live` has not been run. |
| GitHub Issues adapter | **Built, never called.** Tested with a fake HTTP transport. `pytest -m github_live` has not been run. |
| Live AI evaluation | **Not run** (`make eval-live`; needs `ANTHROPIC_API_KEY`). |
| Prompt-only baseline | **Not run** (live only; outputs are never simulated). |
| LLM judge for citation support | **Not implemented and not run.** Support labels are by the build agent, not human-reviewed. |
| Dataset labels | **Not human-reviewed.** |
| Cost estimates | Shown only if `LIVE_PRICE_*` is set. No prices are assumed. |
| Sending replies to customers | Not implemented. Approved replies are recorded, never sent. |
| Concurrency and rate limits across several API instances | Not supported (single instance assumed). |
