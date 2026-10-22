# Verification (SPEC §15): Milestone 5 final run

Date: 2026-10-22. Environment: macOS, Docker Compose. **No `ANTHROPIC_API_KEY` and no GitHub token**, so everything
below ran in demo mode, and every live or GitHub item is marked unverified.

## Commands run, in README order, from a clean state

| Step | Command | Result |
|---|---|---|
| Env file | `cp .env.example .env` | created (no `.env` existed) |
| Clean start | `make reset` (`docker compose down -v && docker compose up -d --build`) | db healthy, api healthy, web `200` on http://localhost:8080 |
| Re-seed | `make seed` | `seed: Northstar Analytics loaded` / `seed: Lumen Ledger loaded` |
| Backend tests | `make test` | **121 passed**, 5 deselected (opt-in `live` / `github_live` smoke tests that need real credentials) |
| Frontend | `make test-web` (`npm ci && npm run typecheck && npm run build`) | typecheck clean; production build OK (308.6 kB JS, 90.9 kB gzip) |
| Browser checks | `make e2e` (CLI `playwright-core`, headless Chromium) | **50/50 passed** (40 from M1–M4 plus 10 new M5 dashboard, width and accessibility checks) |
| Evaluation | `make eval` | AI eval demo: run (Simulated, not evidence of AI performance). AI eval live: **not run** (no key). Backend checks: **64/64 passed**. Results in `eval/results/*-2026-10-22.json` at commit `d6b8d5c` |
| Stop / start keeps data | `make down` then `make up` | support_requests 21 before, 21 after; web `200` |

The stack was left running in demo mode.

## SPEC §15 checklist

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Fresh startup loads the seeded inbox | ✅ | Browser: `seeded inbox loads (6 requests)`, `mode banner shows demo mode` (after `make reset`) |
| 2 | All three demo scenarios work | ✅ | Browser: `access reply uses account facts`, `billing reply lists real invoices and asks to confirm`, `escalation: one ticket after approve + repeated approve`. Eval cases ev-001 (resolve), ev-003 (clarify), ev-004 (escalate, Engineering — Data Connectors / high) match their labels |
| 3 | Approval creates exactly one ticket and an audit record | ✅ | Tests: `test_approval.py::test_audit_trail_covers_every_step`, `test_duplicates.py::test_double_approve_creates_one_ticket`, `::test_concurrent_approvals_create_one_ticket`. Browser: `approved edited version creates exactly one ticket`, `audit records approval and execution`. Eval: ev-047–050 execution steps 4/4 (one ticket each) |
| 4 | Editing a proposal requires renewed approval | ✅ | Tests: `test_approval.py::test_edit_invalidates_and_old_version_cannot_be_approved`, `::test_edit_after_failure_requires_new_approval`, `::test_action_hash_must_match`. Browser: `approving the pre-edit version is refused` |
| 5 | Replacing a policy prevents stale pending proposals from executing | ✅ | Tests: `test_stale.py::test_replacement_marks_pending_stale_in_same_transaction`, `::test_stale_cannot_be_approved_and_reprocess_creates_new_version`, `::test_deleting_a_document_stales_proposals_that_used_it`. Browser: `pending proposal shows stale after the policy doc is replaced`, `approving the stale proposal is refused by the server`. Eval: ev-030/031/032 `execute_on_stale_evidence` pass (409, 0 executions) |
| 6 | Missing evidence produces clarification or escalation | ✅ | Tests: `test_evidence.py::test_insufficient_evidence_forces_escalation`, `::test_conflicting_documents_force_escalation`, `::test_evidence_guard_overrides_a_forced_resolve`, `::test_reviewer_edit_cannot_turn_unsupported_evidence_into_resolve`, `test_proposals.py::test_no_evidence_means_no_resolve`. Browser: `conflicting documents are flagged and the proposal escalates`. Eval: ev-024/025 (insufficient) and ev-027/028 (conflicting) escalate. Caveat: the raw-message probe shows the threshold also over-escalates answerable questions (eval/RESULTS.md) |
| 7 | Injected instructions cannot bypass approval | ✅ for code paths; ⚠️ live model unverified | Tests (fake SDK client scripted to obey the injection): `test_live_security.py::test_injection_in_request_cannot_approve_or_refund`, `::test_injection_in_retrieved_document_is_data_only`, `::test_security_rule_applies_despite_model`, `::test_authority_arguments_are_refused`. Eval: ev-033, ev-036, ev-037 with no approval, execution or ticket after the run and no foreign identifiers. A real model's resistance to injection has **not** been tested |
| 8 | Customer and workspace isolation hold | ✅ | Tests: `test_authorization.py::test_tools_scope_to_authorized_customer`, `::test_mentioned_email_does_not_grant_access`, `::test_reviewer_with_unknown_or_foreign_customer_is_refused`, `test_workspaces.py::test_customer_ids_do_not_cross_workspaces`, `::test_reviewer_of_lumen_cannot_read_import_or_approve_in_northstar`, `::test_retrieval_never_crosses_workspaces`, `::test_citation_from_another_workspace_is_rejected`. Eval: gate refusals ev-038, 039, 041, 043, 044 (403); `cross_customer_facts` 29/29 pass |
| 9 | Visitor demo sessions are isolated | ✅ | Tests: `test_demo_sessions.py::test_reset_only_affects_own_session`, `test_authorization.py::test_visitor_cannot_see_reviewer_or_other_visitor_rows`, `test_workspaces.py::test_visitor_sandboxes_are_per_workspace_and_reset_only_the_caller`, `test_dashboard.py::test_visitor_dashboard_counts_only_own_sandbox`. Browser: `visitor B does not see visitor A's requests`, `visitor B cannot open A's request`, `reset leaves B's session intact`, `dashboard: another visitor sees none of the first visitor's activity` |
| 10 | Missing credentials leave demo mode usable | ✅ | This entire run had no Anthropic key and no GitHub token: all 50 browser checks and the demo eval ran. Tests: `test_live_provider.py::test_missing_key_is_a_clear_configuration_error` (live mode without a key → `error` state with a clear message, no fallback). Browser: `reviewer adapter step: GitHub not configured, with the server's reason`; dashboard live cost reads `pricing not configured` |
| 11 | Switching companies changes answers according to their documents | ✅ | Tests: `test_evidence.py::test_same_access_wording_different_company_different_answer`, `::test_same_billing_wording_different_company_different_answer`, `::test_same_refund_wording_routes_by_each_companys_rules`. Browser: `switching company: same wording, different cited docs and answer`. Eval: ev-001 vs ev-009, ev-003 (clarify) vs ev-010 (resolve), ev-005 (Billing/normal) vs ev-012 (Accounts Receivable/high) |
| 12 | Setup instructions match actual behaviour | ✅ | Every command in the README task table was run literally from a clean state (table above). One README correction in M5: the browser check needs freshly seeded data, so it is now documented as "run after `make reset`" |

## Also verified in M5

- Dashboard (`backend/tests/test_dashboard.py`, 3 tests; browser checks `dashboard (visitor)…`, `(reviewer)…`,
  `…simulated and live usage separate…`, `…eval results are labelled by mode…`).
- Widths 1440, 1024 and 390 have no horizontal overflow for the workspace and the dashboard (browser). Every control
  has an accessible name, and keyboard focus is visible (browser).
- Polish fixes found in review: timeline tool names overlapped results (fixed; they now break at underscores);
  muted text `zinc-400` → `zinc-500` for contrast on white; `<summary>` focus ring; the header wraps at 390px
  (the new Dashboard button had caused 18–23px overflow).

## Not verified (needs credentials or a human)

- Live Claude calls: `pytest -m live`, `make eval-live` (live AI eval and the prompt-only baseline).
- GitHub Issues against real GitHub: `pytest -m github_live`.
- Human review of the dataset labels and the citation-support labels. No LLM judge exists.
- Visual QA used the repo's CLI `playwright-core` scripts. The Playwright MCP navigate tool was tried once, but it
  writes snapshot files into the launching agent's working directory (outside this repo), so it was abandoned
  and that file removed.
