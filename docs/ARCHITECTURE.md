# Architecture

ResolveOps is three containers plus an evaluation package. The rule the whole design follows: **the AI
proposes, ordinary code decides.** Identity, permissions, escalation rules, evidence sufficiency, citation
validity, approval and execution are all enforced in Python, never by the model.

## 1. Containers

```mermaid
flowchart LR
  B[Browser<br/>React 19 + Vite build] -->|/ and /api via nginx| W[web<br/>nginx :8080]
  W -->|/api/*| A[api<br/>FastAPI, Python 3.12 :8000]
  A --> D[(db<br/>Postgres 17 + pgvector)]
  A -. live mode only, reviewers .-> C[Anthropic API<br/>Claude]
  A -. optional, escalations only .-> G[GitHub Issues API<br/>one allowlisted test repo]
  E[eval/ package<br/>mounted at /srv/eval] -->|runs in the api container| A
  E -->|resolveops_eval DB| D
```

- `docker-compose.yml`: `db` (pgvector image, named volume `pgdata`), `api` (built from `backend/`, runs
  migrations then seeds on first start via `start.sh`), `web` (built from `frontend/`, nginx serving the build and
  proxying `/api`).
- The embedding model (`BAAI/bge-small-en-v1.5`, 384-dim, `fastembed`) is baked into the api image, so
  retrieval needs no network.
- Test and eval suites use their own databases (`resolveops_test`, `resolveops_eval`) on the same server. They
  never touch the demo data.

## 2. Request workflow (explicit state machine, `backend/app/workflow.py`)

```mermaid
stateDiagram-v2
  [*] --> received
  received --> classified
  received --> unsupported: demo text without fixture / out of scope / no customer
  received --> error: provider error (no fallback)
  classified --> context_resolved: tools (customer, subscription, tickets)
  classified --> unsupported
  classified --> error
  context_resolved --> retrieved: search_knowledge_base
  context_resolved --> error
  retrieved --> awaiting_review: proposal v1 (validated, rules + evidence applied)
  retrieved --> error
  awaiting_review --> awaiting_review: edit → v(n+1), earlier approvals invalid
  awaiting_review --> approved: approve(version id + action hash)
  awaiting_review --> rejected
  awaiting_review --> stale: cited/retrieved doc replaced or deleted, matching rules changed
  approved --> executing
  executing --> completed: one ticket (idempotency key)
  executing --> failed: bounded attempts exhausted
  failed --> executing: retry (same key)
  failed --> awaiting_review: edit → needs new approval
  failed --> stale
  rejected --> received: reprocess
  stale --> received: reprocess → next version of the same proposal
  error --> received: reprocess
  unsupported --> received: reprocess
  completed --> [*]
```

`TRANSITIONS` in `workflow.py` is the single table of legal moves. `transition()` refuses anything else and
audits every move.

## 3. One request through the code

```mermaid
flowchart TD
  S["POST /api/w/{ws}/requests<br/>api/requests.py:submit"] -->|customer from server session<br/>or reviewer-selected id in this workspace| R[workflow.run_request]
  R --> P{providers.get_provider}
  P -->|demo| SIM[SimulatedProvider<br/>fixtures from sim_fixtures]
  P -->|live, reviewers| LIVE[LiveProvider.run_agent<br/>bounded tool loop]
  SIM --> STEP[_run_stepwise: server calls tools]
  LIVE --> GATE[ToolGate.run<br/>allowlist · no authority args · own tickets only]
  GATE --> T
  STEP --> T[tools.call_tool<br/>lookup_customer · get_subscription · get_existing_tickets · search_knowledge_base]
  T --> CTX[(ToolContext: workspace_id + customer_id<br/>from the request row, never from the model)]
  T --> RET[retrieval.search<br/>pgvector cosine, active chunks of this workspace]
  STEP --> SYN[provider.synthesize → draft]
  LIVE --> SYN2[final JSON → schema-validated draft]
  SYN --> V
  SYN2 --> V
  V[validate_citations: keep only retrieved chunks] --> AF[account_facts: built from tool output]
  AF --> PT1[propose_ticket_action: validate draft]
  PT1 --> EV[evidence.assess + evidence.apply<br/>insufficient / conflicting → escalate]
  EV --> NR[no citations + resolve → escalate]
  NR --> RU[apply_rules: rules.evaluate overrides model]
  RU --> PT2[propose_ticket_action: validate final action]
  PT2 --> SV[save_version + ProposalEvidence rows]
  SV --> AR[awaiting_review]
  AR --> AP["review.approve<br/>lock row · not stale · version id + action_hash match · one active approval"]
  AP --> EX[review._run_execution<br/>savepoint per attempt · bounded retries]
  EX --> AD{adapter}
  AD --> INT[adapters/internal.py<br/>UNIQUE idempotency_key]
  AD --> GH[adapters/github.py<br/>marker lookup before every send]
```

## 4. Tool gate and provider interface

- **Provider interface** (`providers/base.py`): `AIProvider.classify`, `synthesize`, and for agentic providers
  `run_agent`. Providers interpret language and draft. They never authorize, validate, approve or execute.
  `ProviderError` is surfaced as the `error` state. There is no simulated fallback.
  - `SimulatedProvider` (`providers/simulated.py`): exact-match fixtures per workspace, rendered from tool results
    and retrieved passages; cites a section only if retrieval returned it. Unknown text raises `UnsupportedInDemo`.
  - `LiveProvider` (`providers/live.py`): Claude via the official SDK, tool use, structured final output, bounded
    retries, per-request token cap. Prompt construction is in `providers/live_prompt.py`.
- **Tool gate** (`providers/live_guard.py:ToolGate.run`): every model-requested tool call passes through it. It
  refuses tools not on the allowlist, refuses arguments that try to set identity
  (`customer_id`, `workspace_id`, …), and refuses ticket ids that are not the authorized customer's. Each refusal
  is audited.
- **Tools** (`tools.py`): typed Pydantic arguments, `ToolContext` carries the trusted scope, and every query
  filters by `workspace_id` and the authorized `customer_id` (`_require_customer`). `lookup_customer` reports
  mentioned foreign emails as "not accessed" and never looks them up. `propose_ticket_action` validates and
  never writes.

## 5. Evidence and staleness checks

```mermaid
flowchart LR
  subgraph Proposal creation
    PS[retrieved passages] --> AS[evidence.assess<br/>score ≥ RETRIEVAL_MIN_SCORE?<br/>policy-fact conflicts?]
    AS -->|sufficient| OK[keep drafted action]
    AS -->|insufficient / conflicting| ESC[evidence.apply → escalate<br/>holding reply, evidence-review group]
  end
  subgraph Document lifecycle
    UP[documents.create_replacement / delete_document] --> IV[documents.index_version<br/>new chunks, old chunks inactive]
    IV --> ST[staleness.invalidate_for_document_versions<br/>same transaction]
    RC[rule create/update/delete] --> SR[staleness.invalidate_for_rule_change]
  end
  ST --> MK[mark_stale: proposal + request → stale, approvals invalidated]
  SR --> MK
  MK --> RF[review._refuse_if_stale<br/>approve / edit / retry refused 409]
```

- Every proposal version records the exact document versions and chunks it retrieved and cited
  (`ProposalEvidence`). Replacing or deleting a document marks every pending proposal that used it as stale in
  the same database transaction.
- Citations always open the exact version they cite (`GET /api/w/{ws}/chunks/{id}`), labelled superseded or
  deleted when it is no longer current.

## 6. Scoping (who sees what)

- `context.py:actor_for_workspace` resolves each request to an `Actor`: a **reviewer** (member of this
  workspace) or a **visitor** (demo session in a demo-enabled workspace). Anything else gets 401.
- `context.py:scope_clause` limits session-scoped tables (requests, executions, tickets, AI runs, audit) to the
  caller's demo session, or to the workspace queue for reviewers. The inbox, request detail, tickets and the
  dashboard all use it.
- Visitors never use live mode (`providers.live_for`), never reach admin routes (`require_reviewer`), and never
  use GitHub (`review._adapter_name`).

## 7. Evaluation (`eval/`)

- `run_ai_eval.py`: drives each case in `datasets/v1/cases.jsonl` through the real HTTP API (in-process
  TestClient) against `resolveops_eval`, then computes metrics (`metrics.py`). Demo results are labelled
  simulated. Live needs a key. `baseline.py` is the prompt-only comparison (live only).
- `run_backend_eval.py`: runs 64 selected backend tests, grouped into SPEC §13 categories.
- Results go to `eval/results/<suite>-<mode>-<date>.json`. The dashboard reads the latest per suite and mode.
  Write-up: `eval/RESULTS.md`.

Design decisions and tradeoffs: [`DECISIONS.md`](DECISIONS.md) (D1–D33).
