"""Turn per-case results into the reported metrics. Pure functions; no app imports."""
import json
from collections import Counter, defaultdict
from statistics import mean, median

from .harness import DATASET_DIR


def _rate(num: int, den: int) -> dict:
    return {"correct": num, "total": den, "rate": round(num / den, 3) if den else None}


def load_support_labels(version: str) -> dict:
    path = DATASET_DIR / version / "support_labels.jsonl"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out[(row["workspace"], row["doc"], row["section"], row["claim"])] = row
    return out


def summarize(cases: list[dict], results: dict, version: str) -> dict:
    by_id = {c["id"]: c for c in cases}
    cov = Counter(r["observed"]["coverage"] for r in results.values())
    scored = [i for i, r in results.items() if r["observed"]["coverage"] in ("evaluated", "gate")]
    evaluated = [i for i, r in results.items() if r["observed"]["coverage"] == "evaluated"]
    with_proposal = [i for i in evaluated if results[i]["observed"].get("citations") is not None]

    # next action
    act_ok = [i for i in scored if results[i]["observed"]["next_action"] == by_id[i]["expected_next_action"]]
    model_path = [i for i in with_proposal]  # cases where a (simulated or live) provider drafted a proposal
    model_ok = [i for i in model_path if i in act_ok]

    # classification
    cls_cases = [i for i in evaluated if by_id[i]["expected_category"] is not None
                 and results[i]["observed"]["category"] is not None]
    cls_ok = [i for i in cls_cases if results[i]["observed"]["category"] == by_id[i]["expected_category"]]

    # retrieval recall over the union of passages retrieved for the request
    doc_recalls, sec_recalls, k_sizes = [], [], []
    for i in with_proposal:
        exp = by_id[i]["expected_relevant_doc_ids"]
        if not exp:
            continue
        got = results[i]["observed"]["retrieved"]
        k_sizes.append(len(got))
        got_docs = {g["doc"] for g in got}
        got_secs = {(g["doc"], g["section"]) for g in got}
        exp_docs = {e["doc"] for e in exp}
        exp_secs = {(e["doc"], e["section"]) for e in exp if e["section"]}
        doc_recalls.append(len(exp_docs & got_docs) / len(exp_docs))
        if exp_secs:
            sec_recalls.append(len(exp_secs & got_secs) / len(exp_secs))

    # retrieval probe: raw message as the query, top_k passages, every message case (no model involved)
    pr_doc, pr_sec, pr_ev = [], [], Counter()
    for i, r in results.items():
        pr = r["observed"].get("retrieval_probe")
        if not pr:
            continue
        exp = by_id[i]["expected_relevant_doc_ids"]
        got_docs = {g["doc"] for g in pr["passages"]}
        got_secs = {(g["doc"], g["section"]) for g in pr["passages"]}
        if exp:
            pr_doc.append(len({e["doc"] for e in exp} & got_docs) / len({e["doc"] for e in exp}))
            secs = {(e["doc"], e["section"]) for e in exp if e["section"]}
            if secs:
                pr_sec.append(len(secs & got_secs) / len(secs))
        t = by_id[i]["case_type"]
        if t in ("insufficient_evidence", "conflicting_evidence"):
            want = "insufficient" if t == "insufficient_evidence" else "conflicting"
            pr_ev["expected_" + want] += 1
            pr_ev["flagged_" + want] += pr["evidence_status"] == want
        elif exp:
            pr_ev["answerable_cases"] += 1
            pr_ev["answerable_flagged_insufficient"] += pr["evidence_status"] == "insufficient"

    # citation validity (existence / provenance / currency) — NOT support
    cits = [c for i in with_proposal for c in results[i]["observed"]["citations"]]
    valid = [c for c in cits if c["exists"] and c["in_retrieved_set"] and c["current_version"]]

    # support: human/agent labels for (doc, section, claim) tuples
    labels = load_support_labels(version)
    support = Counter()
    for i in with_proposal:
        ws = by_id[i]["workspace"]
        for c in results[i]["observed"]["citations"]:
            lab = labels.get((ws, c["doc"], c["section"], c["claim"]))
            c["support_label"] = lab["judgement"] if lab else "unlabelled"
            support[c["support_label"]] += 1

    # clarification / escalation
    def rate_for(expected: str) -> dict:
        ids = [i for i in scored if by_id[i]["expected_next_action"] == expected]
        return _rate(sum(results[i]["observed"]["next_action"] == expected for i in ids), len(ids))
    over_esc = [i for i in scored if by_id[i]["expected_next_action"] in ("resolve", "clarify")
                and results[i]["observed"]["next_action"] == "escalate"]
    under_esc = [i for i in scored if by_id[i]["expected_next_action"] == "escalate"
                 and results[i]["observed"]["next_action"] in ("resolve", "clarify")]

    # routing of escalation tickets
    routed = [i for i in with_proposal if by_id[i].get("expected_ticket")
              and results[i]["observed"]["ticket_action"]["type"] == "create_ticket"]
    routed_ok = [i for i in routed if results[i]["observed"]["ticket_action"]["group"] == by_id[i]["expected_ticket"]["group"]
                 and results[i]["observed"]["ticket_action"]["priority"] == by_id[i]["expected_ticket"]["priority"]]

    # must-not constraints and execution steps
    must = defaultdict(Counter)
    for r in results.values():
        for name, verdict in (r["checks"].get("must_not") or {}).items():
            v = "pending" if verdict == "pending" else verdict.split(":")[0]
            must[name]["n/a" if v == "pending" else v] += 1
    execs = [r["checks"]["execution"] for r in results.values()
             if r["checks"].get("execution") and r["checks"]["execution"].get("passed") is not None]

    # per case type
    per_type = defaultdict(lambda: Counter())
    for i, r in results.items():
        t = by_id[i]["case_type"]
        per_type[t]["cases"] += 1
        per_type[t][r["observed"]["coverage"]] += 1
        if i in act_ok:
            per_type[t]["next_action_correct"] += 1

    runs = [results[i]["observed"].get("ai_run") for i in evaluated if results[i]["observed"].get("ai_run")]
    lat = [x["latency_ms"] for x in runs if x and x.get("latency_ms") is not None]
    tok_in = [x["input_tokens"] for x in runs if x]
    tok_out = [x["output_tokens"] for x in runs if x]

    return {
        "coverage": dict(cov),
        "next_action": {"all_scored_cases": _rate(len(act_ok), len(scored)),
                        "proposal_cases_only": _rate(len(model_ok), len(model_path))},
        "classification_accuracy": _rate(len(cls_ok), len(cls_cases)),
        "retrieval_recall": {
            "definition": "share of labelled relevant docs / sections present in the union of passages retrieved for "
                          "the request (top_k per search query, deduplicated)",
            "cases": len(doc_recalls), "doc_level_mean": round(mean(doc_recalls), 3) if doc_recalls else None,
            "section_level_mean": round(mean(sec_recalls), 3) if sec_recalls else None,
            "mean_passages_retrieved_k": round(mean(k_sizes), 1) if k_sizes else None},
        "retrieval_probe_raw_message": {
            "definition": "retrieval with the raw subject+message as the single query (top_k), no model; covers every "
                          "case submitted with a message, including those demo fixtures cannot draft for",
            "cases_with_labels": len(pr_doc), "doc_recall_mean": round(mean(pr_doc), 3) if pr_doc else None,
            "section_recall_mean": round(mean(pr_sec), 3) if pr_sec else None, "evidence_check": dict(pr_ev)},
        "citation_validity": {"citations": len(cits), "exist": sum(c["exists"] for c in cits),
                              "in_retrieved_set": sum(c["in_retrieved_set"] for c in cits),
                              "current_version": sum(c["current_version"] for c in cits),
                              "valid_all_three": len(valid),
                              "rejected_by_server": sum(results[i]["observed"].get("rejected_citations") or 0
                                                        for i in with_proposal)},
        "citation_support": {"labels": dict(support),
                             "note": "Judgements from eval/datasets/<v>/support_labels.jsonl (labelled by the build "
                                     "agent, not yet human-reviewed). LLM judge: not run."},
        "clarification_escalation": {"clarify_when_expected": rate_for("clarify"),
                                     "escalate_when_expected": rate_for("escalate"),
                                     "refuse_when_expected": rate_for("refuse"),
                                     "error_when_expected": rate_for("error"),
                                     "over_escalations": sorted(over_esc), "under_escalations": sorted(under_esc)},
        "escalation_routing": _rate(len(routed_ok), len(routed)),
        "must_not": {k: dict(v) for k, v in sorted(must.items())},
        "execution_steps": {"passed": sum(bool(e["passed"]) for e in execs), "total": len(execs)},
        "per_case_type": {k: dict(v) for k, v in sorted(per_type.items())},
        "latency_tokens": {"runs": len(runs), "latency_ms_median": median(lat) if lat else None,
                           "latency_ms_max": max(lat) if lat else None,
                           "input_tokens_total": sum(tok_in), "output_tokens_total": sum(tok_out)},
    }
