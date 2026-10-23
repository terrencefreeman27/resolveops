"""Dashboard metrics, scoped exactly like the inbox.

- A visitor sees metrics for their own demo sandbox only (rows tagged with their demo session).
- A reviewer sees the workspace queue (rows with no demo session) of a workspace they belong to.
No cross-sandbox aggregates are exposed: visitor activity stays private to each visitor (DECISIONS D31).

Simulated and live AI runs are reported separately and never summed. Cost appears only when both
LIVE_PRICE_* variables are set, with those assumptions returned alongside. Evaluation results are read from
eval/results (mounted at /srv/eval/results) and labelled by mode; they describe the synthetic dataset, not
this workspace's traffic.
"""
import json
from pathlib import Path
from statistics import median

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import limits
from ..config import get_settings
from ..context import Actor, actor_for_workspace, scope_clause
from ..db import get_db
from ..models import AiRun, Approval, Execution, Proposal, ProposalVersion, SupportRequest

router = APIRouter(prefix="/api/w/{ws}")
RESULTS_DIR = Path("/srv/eval/results")


def _p95(values: list[int]):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def _runs(db: Session, actor: Actor) -> dict:
    s = get_settings()
    rows = db.scalars(select(AiRun).where(AiRun.workspace_id == actor.workspace_id, scope_clause(actor, AiRun))).all()
    out = {}
    for kind in ("simulated", "live"):
        rs = [r for r in rows if r.provider == kind]
        lat = [r.latency_ms for r in rs if r.latency_ms is not None and r.status != "running"]
        block = {"runs": len(rs), "succeeded": sum(r.status == "succeeded" for r in rs),
                 "errors": sum(r.status == "error" for r in rs),
                 "latency_ms_median": median(lat) if lat else None, "latency_ms_p95": _p95(lat)}
        if kind == "live":
            unc, tout = sum(r.input_tokens for r in rs), sum(r.output_tokens for r in rs)
            cread = sum(r.cache_read_input_tokens for r in rs)
            cwrite = sum(r.cache_creation_input_tokens for r in rs)
            block |= {"input_tokens": unc + cread + cwrite, "uncached_input_tokens": unc, "output_tokens": tout,
                      "cache_read_input_tokens": cread, "cache_creation_input_tokens": cwrite}
            cost = limits.cost_usd(unc, tout, s, cache_read_tokens=cread, cache_write_tokens=cwrite)
            block["cost"] = ({"usd": round(cost, 4), "assumptions": {
                "input_per_mtok_usd": s.live_price_input_per_mtok, "output_per_mtok_usd": s.live_price_output_per_mtok,
                "source": "LIVE_PRICE_* environment variables (operator-configured)",
                "cache_read_multiplier": s.live_price_cache_read_multiplier,
                "cache_write_multiplier": s.live_price_cache_write_multiplier,
                "excludes": "long-prompt (>100K) tier pricing, taxes, and anything not in the API usage fields"}}
                if cost is not None else {"usd": None, "note": "pricing not configured"})
        else:
            block["note"] = ("Pipeline time with the simulated provider (retrieval, tools, database). "
                             "Not model latency; no tokens are used.")
        out[kind] = block
    return out


def _eval_results() -> dict:
    """Latest result file per suite+mode, reduced to headline numbers."""
    if not RESULTS_DIR.is_dir():
        return {"available": False, "note": "No evaluation results found (eval/results is not mounted or empty)."}
    latest: dict[str, Path] = {}
    for p in sorted(RESULTS_DIR.glob("*.json")):
        suite_mode = p.stem.rsplit("-", 3)[0]  # e.g. ai-demo-2026-10-22 -> ai-demo
        latest[suite_mode] = p
    out = {"available": bool(latest), "suites": []}
    for key, p in sorted(latest.items()):
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        item = {"file": p.name, "suite": d.get("suite"), "mode": d.get("mode"), "status": d.get("status"),
                "label": d.get("label"), "run_at": d.get("run_at"), "git_commit": d.get("git_commit"),
                "dataset_version": d.get("dataset_version"), "command": d.get("command")}
        if d.get("suite") == "ai" and d.get("status") == "run":
            sm = d["summary"]
            item["headline"] = {
                "coverage": sm["coverage"], "next_action": sm["next_action"]["all_scored_cases"],
                "classification": sm["classification_accuracy"],
                "recall_section_mean": sm["retrieval_recall"]["section_level_mean"],
                "citations_valid": f"{sm['citation_validity']['valid_all_three']}/{sm['citation_validity']['citations']}",
                "citation_support_labels": sm["citation_support"]["labels"],
                "clarify_when_expected": sm["clarification_escalation"]["clarify_when_expected"],
                "escalate_when_expected": sm["clarification_escalation"]["escalate_when_expected"],
                "must_not_failures": sum(v.get("fail", 0) for v in sm["must_not"].values())}
            item["baseline"] = (d.get("baseline") or {}).get("status")
        if d.get("suite") == "backend" and d.get("status") == "run":
            item["headline"] = {"totals": d["totals"],
                                "categories": {k: f"{v['passed']}/{v['total']}" for k, v in d["categories"].items()}}
        out["suites"].append(item)
    return out


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(actor_for_workspace), db: Session = Depends(get_db)):
    req_scope = (SupportRequest.workspace_id == actor.workspace_id, SupportRequest.is_template.is_(False),
                 scope_clause(actor, SupportRequest))
    by = db.execute(select(SupportRequest.category, SupportRequest.state, func.count())
                    .where(*req_scope).group_by(SupportRequest.category, SupportRequest.state)).all()
    by_category, by_state = {}, {}
    for cat, state, n in by:
        by_category[cat or "unclassified"] = by_category.get(cat or "unclassified", 0) + n
        by_state[state] = by_state.get(state, 0) + n

    scoped_ids = select(SupportRequest.id).where(*req_scope)
    approvals = db.execute(select(Approval, ProposalVersion.author)
                           .join(ProposalVersion, ProposalVersion.id == Approval.proposal_version_id)
                           .where(Approval.request_id.in_(scoped_ids))).all()
    approved = [(a, author) for a, author in approvals if a.decision == "approved"]
    outcomes = {
        "approved_as_drafted": sum(author.startswith("ai:") for _, author in approved),
        "edited_then_approved": sum(not author.startswith("ai:") for _, author in approved),
        "rejected": sum(a.decision == "rejected" for a, _ in approvals),
        "approvals_invalidated": sum(a.status == "invalidated" for a, _ in approvals),
        "proposals_made_stale": db.scalar(select(func.count()).select_from(Proposal).where(
            Proposal.request_id.in_(scoped_ids), Proposal.stale_at.is_not(None))) or 0,
    }
    execs = db.scalars(select(Execution).where(Execution.request_id.in_(scoped_ids))
                       .order_by(Execution.created_at.desc())).all()
    executions = {"total": len(execs), "succeeded": sum(e.status == "succeeded" for e in execs),
                  "failed": sum(e.status == "failed" for e in execs),
                  "attempts_total": sum(e.attempts for e in execs),
                  "recent_failures": [{"adapter": e.adapter, "attempts": e.attempts, "error": (e.last_error or "")[:160],
                                       "at": e.created_at.isoformat()} for e in execs if e.status == "failed"][:5]}
    return {
        "scope": ("Your demo sandbox only" if actor.demo_session_id is not None
                  else "Workspace queue (reviewer activity; visitor sandboxes excluded)"),
        "requests": {"total": sum(by_state.values()), "by_category": by_category, "by_state": by_state},
        "approval_outcomes": outcomes,
        "executions": executions,
        "ai_runs": _runs(db, actor),
        "evaluation": _eval_results(),
    }
