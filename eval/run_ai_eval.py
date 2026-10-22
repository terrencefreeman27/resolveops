"""AI task evaluation over the versioned dataset.

    docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode demo
    docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api python -m eval.run_ai_eval --mode live

Demo mode drives every case through the real API with the *simulated* provider. Simulated output comes from
fixtures written for the seeded scenarios, so demo results are labelled "Simulated — not evidence of AI
performance", and cases the fixtures don't cover are reported as "unsupported in demo mode" (excluded from
the rates, never counted as passes or failures).

Live mode needs ANTHROPIC_API_KEY (and AI_MODE is forced to live for this process only). Without a key, the
results file records status "not run" and the exact command. Live mode also runs the prompt-only baseline.
"""
import argparse
import os
import sys
import time

from . import harness

SIMULATED_LABEL = "Simulated — not evidence of AI performance"
LIVE_CMD = ("docker compose exec -e EVAL_GIT_COMMIT=$(git rev-parse --short HEAD) api "
            "python -m eval.run_ai_eval --mode live")


def _header(mode: str, version: str) -> dict:
    return {"suite": "ai", "mode": mode, "dataset_version": version, "git_commit": harness.git_commit(),
            "run_at": harness.now_iso(),
            "label": SIMULATED_LABEL if mode == "demo" else "Live model output (Claude); see caveats"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "live"], required=True)
    ap.add_argument("--dataset", default="v1")
    ap.add_argument("--no-baseline", action="store_true", help="live mode: skip the prompt-only baseline")
    args = ap.parse_args(argv)

    if args.mode == "live" and not os.environ.get("ANTHROPIC_API_KEY"):
        payload = _header("live", args.dataset) | {
            "status": "not run", "reason": "ANTHROPIC_API_KEY is not set in the api container.",
            "command": LIVE_CMD, "baseline": {"status": "not run", "command": LIVE_CMD}}
        path = harness.write_result("ai", "live", payload)
        print(f"Live AI eval NOT RUN (no ANTHROPIC_API_KEY). Wrote {path}")
        return 0

    harness.prepare_database(ai_mode=args.mode)
    from app.config import get_settings

    from .ai_runner import Runner
    from .metrics import summarize

    s = get_settings()
    if args.mode == "live":
        # Eval-only overrides for this process: let the case actors reach the live model and avoid the
        # interactive per-minute rate limits. Token budget and per-request caps stay in force.
        for k, v in {"live_allow_visitors": True, "live_rate_per_reviewer_per_min": 10_000,
                     "live_rate_global_per_min": 10_000}.items():
            setattr(s, k, v)

    cases = harness.load_cases(args.dataset)
    runner = Runner()
    mutating = lambda c: bool({"supersede_after_proposal", "inject_document"} & set(c.get("scenario") or {}))  # noqa: E731
    ordered = [c for c in cases if not mutating(c)] + [c for c in cases if mutating(c)]
    results = {}
    started = time.perf_counter()
    for c in ordered:
        try:
            results[c["id"]] = runner.run_case(c)
        except Exception as exc:  # a harness failure is reported, not hidden
            results[c["id"]] = {"observed": {"coverage": "harness_error", "next_action": None, "category": None,
                                             "error": f"{type(exc).__name__}: {exc}"[:500]}, "checks": {}}
        o = results[c["id"]]["observed"]
        print(f"{c['id']:7} {c['case_type']:22} {str(o['coverage']):20} expected={c['expected_next_action']:8} "
              f"observed={o.get('next_action')}")
    results = {c["id"]: results[c["id"]] for c in cases}
    summary = summarize(cases, results, args.dataset)

    payload = _header(args.mode, args.dataset) | {
        "status": "run", "duration_s": round(time.perf_counter() - started, 1),
        "provider": "simulated fixtures (SimulatedProvider)" if args.mode == "demo" else f"live {s.live_model}",
        "summary": summary,
        "cases": [{"id": c["id"], "case_type": c["case_type"], "workspace": c["workspace"],
                   "expected": {"category": c["expected_category"], "next_action": c["expected_next_action"]},
                   **results[c["id"]]} for c in cases],
    }
    if args.mode == "demo":
        payload["baseline"] = {"status": "not run",
                               "reason": "The prompt-only baseline needs a live model; simulating its outputs would "
                                         "be fabrication.", "command": LIVE_CMD}
        payload["live_latency_tokens"] = "not run (demo mode: simulated provider, no model calls)"
    elif not args.no_baseline:
        from .baseline import run_baseline, summarize_baseline
        from app.db import SessionLocal
        from app.models import Workspace
        from sqlalchemy import select

        with SessionLocal() as db:
            names = {w.slug: w.name for w in db.scalars(select(Workspace))}
        bl = run_baseline(cases, names)
        payload["baseline"] = {"status": "run", "summary": summarize_baseline(cases, bl), "cases": bl}
    path = harness.write_result("ai", args.mode, payload)
    print(f"\n{payload['label']}\ncoverage={summary['coverage']} next_action={summary['next_action']}\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
