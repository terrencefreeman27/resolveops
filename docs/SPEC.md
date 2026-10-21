# ResolveOps — Product Specification (source of truth)

Provided by Terrence on 2026-10-21. Every milestone works against this file. Do not weaken requirements; record deviations in `docs/DECISIONS.md` with reasons.

Build a portfolio-quality AI Support Operations Agent called **ResolveOps**.

Act as my implementation partner. Inspect the workspace, make a concise implementation plan, then build, run, and verify the application. Do not stop after planning, scaffolding, or producing a mockup.

Make reasonable decisions and continue without repeatedly asking me to choose implementation details. Follow applicable repository instructions. If the workspace contains another project, create a separate directory and preserve existing work.

## 1. Purpose and scope

I am a computer science student targeting applied AI engineering, automation, and AI solutions roles.

ResolveOps should demonstrate that I can:
- Connect an LLM to business data and tools.
- Retrieve supporting company documentation.
- Coordinate a useful support workflow.
- Enforce permissions and human approval.
- Handle failures.
- Evaluate accuracy and reliability.

Build a focused application that I can demonstrate and explain in interviews.

Complete one excellent end-to-end workflow before expanding features. Avoid unnecessary microservices, multiple agents, Kubernetes, subscription billing, or a generic workflow builder.

The initial supported requests are:
- Account access questions.
- Billing and subscription explanations.
- Product troubleshooting.

Refunds, subscription changes, access grants, outbound email, and unsupported situations require human handling. Customer replies remain drafts in v1.

## 2. Configurable companies

Build a configurable application with a fictional company preloaded, rather than hardcoding the application around that company.

The default workspace is **Northstar Analytics**, a fictional B2B analytics software company.

Store its company profile, customers, subscription records, documents, escalation rules, and integration configuration as workspace-scoped data.

Provide a straightforward reviewer onboarding flow:
1. Create a workspace and enter company details.
2. Import Markdown or plain-text documentation.
3. Review import status and document contents.
4. Configure escalation rules.
5. Select an available ticket adapter.
6. Test a sample support request.

Explain supported file formats in the interface. Do not advertise PDF or other unsupported ingestion.

Include a second small fictional company with different policies to demonstrate that the same request can produce different evidence-based answers in different workspaces.

This is a focused configurable prototype, not a full enterprise SaaS platform.

## 3. Business scenario and seed data

For Northstar Analytics, seed:
- Realistic synthetic customers and subscriptions.
- Incoming support requests.
- Approximately 12–15 concise documents covering plans, billing policies, permissions, troubleshooting, and escalation.
- Existing support tickets.

Keep facts consistent across all records and documentation.

Example request:

"We upgraded yesterday, but two employees still can't access the reporting feature. We already tried signing out."

Account facts should actually affect the proposed resolution.

Include three one-click demonstrations:
1. An access issue addressed using account facts and documentation.
2. A billing question that requires clarification.
3. A product issue escalated into a ticket after approval.

## 4. Preferred stack

Use:
- Python and FastAPI for the backend.
- React, TypeScript, and Tailwind for the frontend.
- PostgreSQL with pgvector for records and semantic retrieval.
- Docker Compose for reproducible startup.
- One LLM provider initially.
- A small explicit workflow/state machine.

Consult current official documentation for SDKs and APIs. Limit dependencies and pin versions appropriately.

## 5. Core workflow

1. Receive a seeded or newly submitted support request.
2. Classify it into a supported category.
3. Determine the authorized customer context and identify missing information.
4. Look up relevant account and subscription facts.
5. Retrieve applicable approved documentation.
6. Generate a validated structured proposal containing:
   - Request summary.
   - Category and priority, with a brief justification.
   - Verified account facts.
   - Draft customer reply.
   - Supporting document citations.
   - Proposed ticket creation or update.
   - Missing information or escalation reason.
7. Present it for human review.
8. Allow the reviewer to edit, approve, or reject it.
9. Execute approved ticket changes.
10. Record the result and any errors.

Use the LLM to interpret language, synthesize evidence, and propose actions. Use application code for authorization, validation, approval, and execution.

Do not use a model's self-reported confidence as the sole reason to execute an action or declare an answer correct.

## 6. Retrieval and document lifecycle

Implement:
- Real embedding-based retrieval in live mode.
- Workspace-scoped document ingestion.
- Document IDs, sections, versions, and import status.
- Clickable citations that open the supporting passage.
- Validation that cited IDs belong to documents retrieved for that request.
- Document replacement and deletion.
- Removal of superseded/deleted content from active retrieval.
- An explicit reprocessing path for requests affected by changed documentation.

Avoid silently using stale policy evidence. Record which document versions supported each proposal.

If documentation is insufficient or conflicting, ask for clarification or escalate.

Treat customer messages and retrieved documents as untrusted data. Instructions inside them must not override system rules or grant permissions.

## 7. Tools and account identity

Implement small, typed tools such as:
- lookup_customer
- get_subscription
- search_knowledge_base
- get_existing_tickets
- propose_ticket_action

Validate tool arguments and outputs.

Enforce both workspace and customer access in backend code. Derive authorization from trusted application context, not model output.

Someone typing another customer's email address must not gain access to that customer's account.

For the prototype:
- Use server-validated synthetic customer sessions for customer submissions.
- Allow authenticated reviewers to select authorized customers within their workspace.
- Clearly label synthetic identities.

Apply authorization to database queries, retrieval, document access, tool execution, and action approval.

## 8. Demo and live modes

The application must work without paid API keys.

**Demo mode:**
- Use synthetic data and deterministic simulated AI outputs.
- Clearly label outputs "Simulated AI — demo mode."
- Exercise the actual database, approval workflow, internal ticket execution, and audit history.
- Include the three demonstration scenarios.
- Clearly handle unsupported demo inputs rather than pretending a live model processed them.

**Live mode:**
- Use a real model API and real embeddings.
- Process newly entered support requests.
- Keep credentials server-side.
- Show clear configuration and provider errors.
- Never silently replace a failed live response with simulated output.

Display the active mode prominently.

## 9. Approval, security, and execution

Enforce these rules in the backend:
- Proposals cannot mutate tickets before approval.
- Approval applies to an exact version of an action.
- Editing an action invalidates its previous approval.
- Relevant policy changes invalidate pending proposals that rely on superseded evidence.
- Repeated approvals and retries cannot create duplicate tickets.
- Only allowlisted tools and validated parameters can execute.
- Use bounded retries and timeouts.
- Record failures and support safe retry or escalation.
- Use transactions and execution identifiers where appropriate.
- Do not execute code or make unrestricted HTTP requests based on model output.

Provide a simple authenticated reviewer role. Protect document imports, workspace settings, credentials, and approvals on the server.

Keep secrets out of frontend bundles, logs, source control, and model prompts.

Do not perform real refunds, access grants, subscription changes, or outbound email.

## 10. Ticket integrations

First implement a functioning internal ticket system behind a small adapter interface.

Then implement an optional GitHub Issues adapter for a dedicated test repository:
- Approved escalations can create an issue.
- Store the external issue ID and URL.
- Handle failures and duplicate execution.
- Keep credentials in environment variables.
- Restrict the configured destination.

If credentials are unavailable, finish and verify the internal adapter. Clearly identify the external integration as unverified.

Do not block the working application or claim an integration passed testing without actually testing it.

## 11. Interface and demonstration experience

Create a polished support workspace:
- Inbox and filters on the left.
- Selected request and proposed resolution in the center.
- Account facts, sources, and action history on the right.
- Clear status indicators.
- Edit, approve, reject, and retry controls.
- An expandable activity timeline with tool names, concise results, citations, timing, and errors.

Show concise decision summaries and evidence. Do not request or expose private model chain-of-thought.

Include a dashboard showing:
- Requests by category and state.
- Approval outcomes.
- Execution failures.
- Latency and token usage when available.
- Evaluation results.

Keep simulated and live metrics separate. Only estimate model cost when pricing is configured, and display the pricing assumptions. Never invent savings or business impact.

A visitor should be able to open the demo and try a seeded scenario without registration, API keys, or connecting company systems.

Keep visitor demo activity isolated from real integrations and from other visitors. Provide a reset function that only resets the current demo session.

Public visitors must not be able to upload documents, change workspace settings, access credentials, or execute real integrations.

## 12. Usage and spending controls

Implement:
- Input and upload size limits.
- Rate limits for live model calls.
- Per-request token/output limits.
- A configurable live usage budget.
- Concurrency limits.
- Clear behavior when limits are reached.

Keep live usage disabled for public visitors by default.

Document how to enable it deliberately. Do not deploy publicly or enable paid external access as part of this task.

## 13. Evaluation and tests

Create a versioned dataset of 50 synthetic labeled support cases covering:
- Normal supported requests.
- Ambiguous or missing information.
- Unsupported questions.
- Insufficient or conflicting evidence.
- Outdated policies.
- Prompt injection attempts.
- Cross-workspace and cross-customer access attempts.
- Missing customer records.
- API failures.
- Duplicate execution attempts.

Include expected categories, relevant sources, and appropriate next actions.

Separate AI task evaluations from deterministic backend authorization and execution tests.

Report:
- Classification accuracy.
- Correct next-action rate.
- Retrieval recall against labeled sources.
- Citation validity.
- Appropriate clarification and escalation.
- Unauthorized action prevention.
- Duplicate prevention.
- Live latency and token usage where available.

Compare a simple prompt-only baseline with the retrieval-and-tools workflow. Document what information each receives and avoid drawing conclusions from an unfair comparison.

Distinguish citation existence checks from whether the evidence actually supports a claim. Document any human review or model-based grading.

Do not fabricate results or present simulated demo evaluations as evidence of live AI performance. If credentials are missing, provide the live evaluation command and label those results "not run."

Add meaningful backend tests for authorization, approval versioning, document lifecycle, and duplicate prevention. Add relevant frontend checks and browser tests for critical workflows where tooling is available.

## 14. Documentation and interview readiness

Provide:
- README with exact setup, startup, shutdown, seed, and reset commands.
- .env.example without secrets.
- Architecture diagram.
- Concise design decisions and tradeoffs.
- Demo/live mode configuration.
- Optional GitHub integration setup.
- Evaluation commands and actual results.
- Known limitations and what a real pilot would still require.
- A short recorded-demo script.

Create an interview walkthrough explaining:
- The business problem.
- One request from intake to completed ticket.
- How retrieval and tool calling work.
- Where ordinary code enforces permissions.
- Why approval is required.
- How failures and duplicates are handled.
- What the evaluation measures.
- Which features are simulated or unverified.

Keep the architecture understandable enough that I can inspect and explain the important paths myself.

## 15. Build sequence and completion checks

Build in milestones:
1. One working vertical slice with seeded data, simulated AI, approval, internal tickets, and audit history.
2. Live retrieval and model/tool integration.
3. Configurable workspace setup, document lifecycle, and second-company demonstration.
4. Optional external adapter.
5. Evaluation, interface polish, and documentation.

Run relevant backend tests, frontend type checks, and a production build. Use browser verification if available.

Verify:
- Fresh startup loads the seeded inbox.
- All three demo scenarios work.
- Approval creates exactly one ticket and an audit record.
- Editing a proposal requires renewed approval.
- Replacing a policy prevents stale pending proposals from executing.
- Missing evidence produces clarification or escalation.
- Injected instructions cannot bypass approval.
- Customer and workspace isolation hold.
- Visitor demo sessions are isolated.
- Missing credentials leave demo mode usable.
- Switching companies changes answers according to their documents.
- Setup instructions match actual behavior.

Investigate blockers and complete independent work before stopping. Be precise about any remaining limitations.

At completion, give me:
- What works.
- Exact commands to launch it and the local URL.
- What you tested and the results.
- What requires credentials or manual verification.
- A brief walkthrough of the main implementation files.
