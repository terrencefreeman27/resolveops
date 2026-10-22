"""Deterministic backend evaluation: authorization, approval and execution guarantees.

    docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_backend_eval

These checks need no API key and involve no model judgement: each one is a pytest test in backend/tests that
drives ordinary application code (FastAPI routes, workflow, review, tools, adapters) against a real Postgres
database (`resolveops_test`, recreated by the test suite). Tests marked "fake SDK" exercise the live-provider
code path with a scripted fake Anthropic client (no network); tests marked "fake HTTP" use a fake GitHub
transport. They prove what the server code does with such responses, not how the real services behave.

The runner groups the tests into the SPEC §13 categories, runs them, and records real pass/fail counts.
"""
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from . import harness

FAKE_SDK = {"test_live_security.py", "test_live_provider.py"}
FAKE_HTTP = {"test_github_adapter.py"}

CATEGORIES: dict[str, list[str]] = {
    "authorization_workspace_isolation": [
        "test_workspaces.py::test_reviewer_of_lumen_cannot_read_import_or_approve_in_northstar",
        "test_workspaces.py::test_created_workspace_is_private_to_its_members",
        "test_workspaces.py::test_retrieval_never_crosses_workspaces",
        "test_workspaces.py::test_citation_from_another_workspace_is_rejected",
        "test_workspaces.py::test_customer_ids_do_not_cross_workspaces",
        "test_authorization.py::test_retrieval_and_passages_are_workspace_scoped",
        "test_workspaces.py::test_visitors_cannot_reach_onboarding",
        "test_authorization.py::test_admin_routes_require_reviewer",
    ],
    "authorization_customer_isolation": [
        "test_authorization.py::test_mentioned_email_does_not_grant_access",
        "test_authorization.py::test_tools_scope_to_authorized_customer",
        "test_authorization.py::test_visitor_cannot_submit_as_arbitrary_customer",
        "test_authorization.py::test_reviewer_with_unknown_or_foreign_customer_is_refused",
        "test_live_security.py::test_cross_customer_email_is_not_looked_up",
        "test_live_security.py::test_authority_arguments_are_refused",
        "test_live_security.py::test_foreign_ticket_id_is_refused_and_never_executed",
    ],
    "visitor_session_isolation": [
        "test_authorization.py::test_visitor_cannot_see_reviewer_or_other_visitor_rows",
        "test_demo_sessions.py::test_reset_only_affects_own_session",
        "test_workspaces.py::test_visitor_sandboxes_are_per_workspace_and_reset_only_the_caller",
        "test_demo_sessions.py::test_visitor_note_on_shared_ticket_uses_sandbox_copy",
        "test_authorization.py::test_no_session_is_rejected",
        "test_authorization.py::test_csrf_header_required",
        "test_github_adapter.py::test_visitor_sandbox_always_uses_internal",
    ],
    "unauthorized_action_prevention": [
        "test_approval.py::test_running_workflow_creates_no_ticket",
        "test_approval.py::test_templates_cannot_be_approved",
        "test_approval.py::test_reject_then_approve_fails",
        "test_approval.py::test_invalid_ticket_destination_rejected_on_edit",
        "test_authorization.py::test_unknown_tool_rejected",
        "test_live_security.py::test_non_allowlisted_tool_is_refused_and_audited",
        "test_live_security.py::test_visitors_never_use_live_mode",
        "test_github_adapter.py::test_destination_cannot_be_overridden_by_proposal_data",
        "test_github_adapter.py::test_adapter_disabled_flag_blocks_github_even_for_reviewers",
    ],
    "approval_versioning": [
        "test_approval.py::test_edit_invalidates_and_old_version_cannot_be_approved",
        "test_approval.py::test_action_hash_must_match",
        "test_approval.py::test_edit_after_failure_requires_new_approval",
    ],
    "stale_evidence_refusal": [
        "test_stale.py::test_replacement_marks_pending_stale_in_same_transaction",
        "test_stale.py::test_stale_cannot_be_approved_and_reprocess_creates_new_version",
        "test_stale.py::test_failed_execution_goes_stale_and_retry_is_refused",
        "test_stale.py::test_rule_change_marks_affected_pending_proposals_stale",
        "test_stale.py::test_deleting_a_document_stales_proposals_that_used_it",
    ],
    "evidence_guard_insufficient_or_conflicting": [
        "test_evidence.py::test_conflicting_documents_force_escalation",
        "test_evidence.py::test_insufficient_evidence_forces_escalation",
        "test_evidence.py::test_evidence_guard_overrides_a_forced_resolve",
        "test_evidence.py::test_reviewer_edit_cannot_turn_unsupported_evidence_into_resolve",
        "test_proposals.py::test_no_evidence_means_no_resolve",
    ],
    "duplicate_prevention": [
        "test_duplicates.py::test_double_approve_creates_one_ticket",
        "test_duplicates.py::test_concurrent_approvals_create_one_ticket",
        "test_duplicates.py::test_adapter_is_idempotent_by_key",
        "test_duplicates.py::test_retry_after_success_is_refused",
        "test_approval.py::test_failure_after_write_rolls_back_then_retry_is_single",
        "test_github_adapter.py::test_double_approve_creates_one_issue",
        "test_github_adapter.py::test_concurrent_approve_creates_one_issue",
        "test_github_adapter.py::test_timeout_after_create_is_recovered_by_marker_lookup",
    ],
    "injection_cannot_bypass_approval": [
        "test_live_security.py::test_injection_in_request_cannot_approve_or_refund",
        "test_live_security.py::test_injection_in_retrieved_document_is_data_only",
        "test_live_security.py::test_security_rule_applies_despite_model",
        "test_authorization.py::test_mentioned_email_does_not_grant_access",
    ],
    "failures_reach_error_state_without_simulated_fallback": [
        "test_proposals.py::test_provider_failure_in_demo_mode_is_an_error_without_fallback",
        "test_live_provider.py::test_retries_exhausted_goes_to_error_without_fallback",
        "test_live_provider.py::test_non_retryable_error_fails_immediately",
        "test_live_provider.py::test_missing_key_is_a_clear_configuration_error",
        "test_live_provider.py::test_refusal_and_max_tokens_are_errors",
        "test_live_provider.py::test_output_failing_schema_is_an_error_not_a_proposal",
        "test_approval.py::test_failure_recorded_then_retry_creates_exactly_one",
        "test_github_adapter.py::test_5xx_exhausted_fails_with_bounded_attempts",
        "test_github_adapter.py::test_permanent_errors_fail_fast_with_recorded_error",
    ],
}


def _kind(nodeid: str) -> str:
    f = nodeid.split("::")[0]
    return "fake SDK (live code path, scripted Anthropic client)" if f in FAKE_SDK else \
        "fake HTTP (GitHub adapter, scripted transport)" if f in FAKE_HTTP else "real code, real Postgres"


def main() -> int:
    nodes = sorted({n for ns in CATEGORIES.values() for n in ns})
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "junit.xml"
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}",
                               *[f"tests/{n}" for n in nodes]], cwd="/srv", capture_output=True, text=True)
        tail = "\n".join(proc.stdout.strip().splitlines()[-3:])
        outcome = {}
        for tc in ET.parse(xml).getroot().iter("testcase"):
            f = tc.get("classname").split(".")[-1] + ".py"
            key = f"{f}::{tc.get('name').split('[')[0]}"  # parametrized cases count as one test
            if tc.find("failure") is not None or tc.find("error") is not None:
                outcome[key] = "failed"
            elif outcome.get(key) == "failed":
                pass
            elif tc.find("skipped") is not None:
                outcome[key] = "skipped"
            else:
                outcome[key] = "passed"
    cats = {}
    for cat, ns in CATEGORIES.items():
        rows = [{"test": n, "result": outcome.get(n, "not collected"), "kind": _kind(n)} for n in ns]
        cats[cat] = {"passed": sum(r["result"] == "passed" for r in rows), "total": len(rows), "tests": rows}
    totals = defaultdict(int)
    for n in nodes:
        totals[outcome.get(n, "not collected")] += 1
    payload = {"suite": "backend", "mode": "deterministic (no model, no keys)", "git_commit": harness.git_commit(),
               "run_at": harness.now_iso(), "status": "run", "pytest_summary": tail,
               "unique_tests": len(nodes), "totals": dict(totals), "categories": cats}
    path = harness.write_result("backend", "deterministic", payload)
    for cat, v in cats.items():
        print(f"{cat:55} {v['passed']}/{v['total']}")
    print(f"unique tests: {dict(totals)}  ({tail.splitlines()[-1] if tail else ''})\nWrote {path}")
    return 0 if totals.get("failed", 0) == 0 and totals.get("not collected", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
