"""Renders a `RunReport` as human-readable text: security-gate summary
(hard pass/fail), per-category metric averages, and a failure-analysis
block per failing case (Milestone 6 design section 17) using only stable
ids and permission-safe fields — never forbidden content, even though the
evaluator privately knows what was supposed to be excluded.
"""

from __future__ import annotations

from app.evaluation.runner import CaseResult, RunReport


def render(report: RunReport) -> str:
    lines: list[str] = []
    lines.append(f"=== Milestone 6 evaluation — mode={report.mode} — {report.timestamp} ===")
    lines.append("")
    lines.extend(_overall_status_section(report))
    lines.append("")
    lines.extend(_security_section(report))
    lines.append("")
    if report.mode == "retrieval":
        lines.extend(_retrieval_metrics_section(report))
        lines.append("")
    if report.mode == "generation":
        lines.extend(_generation_metrics_section(report))
        lines.append("")
        lines.extend(_manual_review_section(report))
        lines.append("")
    if report.freshness_results:
        lines.extend(_freshness_section(report))
        lines.append("")
    lines.extend(_status_summary_section(report))
    lines.append("")
    lines.extend(_failure_section(report))
    return "\n".join(lines)


def _overall_status_section(report: RunReport) -> list[str]:
    return [
        "--- Overall security status ---",
        f"  automated_security_all_clear = {report.automated_security_all_clear}",
        f"  manual_security_review_status = {report.manual_security_review_status}",
        f"  overall_security_status = {report.overall_security_status.upper()}",
    ]


def _security_section(report: RunReport) -> list[str]:
    total_violations = sum(r.security_violation_count for r in report.case_results)
    freshness_violations = sum(
        1 for seq in report.freshness_results for step in seq["steps"]
        if step["security_violations"] != 0 or not step["forbidden_absent"]
    )
    lines = ["--- Automated structural security gates (hard, zero-tolerance) ---"]
    gate_totals: dict[str, int] = {}
    for r in report.case_results:
        for gate, count in r.security.items():
            gate_totals[gate] = gate_totals.get(gate, 0) + count
    for gate, count in gate_totals.items():
        lines.append(f"  {gate} = {count}")
    lines.append(f"  flat-case violations = {total_violations}")
    lines.append(f"  freshness-sequence violations = {freshness_violations}")
    lines.append(
        f"  automated_security_all_clear -> {'PASS' if report.automated_security_all_clear else 'FAIL'} "
        "(includes freshness sequences, not just flat cases)"
    )
    return lines


def _status_summary_section(report: RunReport) -> list[str]:
    lines = ["--- Status/permission correctness per category ---"]
    by_category: dict[str, list[CaseResult]] = {}
    for r in report.case_results:
        by_category.setdefault(r.category, []).append(r)
    for category, results in sorted(by_category.items()):
        n = len(results)
        ok = sum(1 for r in results if r.status_ok)
        lines.append(f"  {category}: {ok}/{n} status-correct")
    return lines


def _retrieval_metrics_section(report: RunReport) -> list[str]:
    lines = ["--- Real retrieval quality (BgeEmbeddingProvider) — NOT computed under security mode ---"]
    by_category: dict[str, list[CaseResult]] = {}
    excluded_categories: set[str] = set()
    for r in report.case_results:
        if r.recall_5 is not None:
            by_category.setdefault(r.category, []).append(r)
        elif r.status_actual != "account_not_visible":
            excluded_categories.add(r.category)
    for category, results in sorted(by_category.items()):
        n = len(results)
        r5 = sum(r.recall_5 for r in results) / n
        r10 = sum(r.recall_10 for r in results) / n
        m = sum(r.mrr for r in results) / n
        lines.append(f"  {category}: recall@5={r5:.2f} recall@10={r10:.2f} mrr={m:.2f} (n={n})")
    still_excluded = sorted(excluded_categories - by_category.keys())
    if still_excluded:
        lines.append(
            f"  (no Recall/MRR-eligible cases — all expected_evidence=[] — in: {still_excluded}; "
            "Recall@k is undefined, not zero, for those cases; see docs/evaluation.md)"
        )
    return lines


def _generation_metrics_section(report: RunReport) -> list[str]:
    lines = ["--- Real generation quality (GeminiAnswerGenerator) ---"]
    scored = [r for r in report.case_results if r.generation is not None]
    for field in ("citation_correct", "citation_complete", "forbidden_absent", "status_correct"):
        n = len(scored)
        passed = sum(1 for r in scored if r.generation["score"].get(field))
        lines.append(f"  {field}: {passed}/{n}")
    for field in ("authority_correct", "temporal_correct"):
        applicable = [r for r in scored if r.generation["score"].get(field) is not None]
        if applicable:
            passed = sum(1 for r in applicable if r.generation["score"][field])
            lines.append(f"  {field}: {passed}/{len(applicable)}")
    return lines


def _manual_review_section(report: RunReport) -> list[str]:
    lines = [f"--- Manual security review (human-adjudicated, hard gate) — status: {report.manual_security_review_status} ---"]
    pending = [r for r in report.case_results if r.manual_review]
    if not pending:
        lines.append("  (no cases required manual review in this run)")
        return lines
    for r in pending:
        for gate, verdict in r.manual_review.items():
            if gate == "notes":
                continue
            lines.append(f"  [{r.case_id}] {gate} = {verdict}")
    unresolved = [
        r.case_id for r in pending
        for gate, v in r.manual_review.items() if gate != "notes" and v == "pending_review"
    ]
    if unresolved:
        lines.append(
            f"  INCOMPLETE — unauthorized_facts_emitted / hidden_conflict_leakage cannot be claimed at 0 until "
            f"these cases are reviewed: {sorted(set(unresolved))}"
        )
        lines.append("  Use: python -m app.evaluation.run --review-case-id ID --review-gate GATE --review-verdict pass|fail")
    else:
        lines.append("  All manual-review cases resolved.")
    return lines


def _freshness_section(report: RunReport) -> list[str]:
    lines = ["--- Permission-freshness sequences ---"]
    for seq in report.freshness_results:
        ok = all(step["status_ok"] and step["forbidden_absent"] and step["security_violations"] == 0 for step in seq["steps"])
        lines.append(f"  [{seq['sequence_id']}] {'PASS' if ok else 'FAIL'}")
        for step in seq["steps"]:
            lines.append(
                f"    {step['t']} ({step['persona']}): status={step['status_actual']} "
                f"status_ok={step['status_ok']} forbidden_absent={step['forbidden_absent']}"
            )
    return lines


def _generation_quality_clean(r: CaseResult) -> bool:
    """`security` mode's generation payload has no "score" key at all (it
    never computes answer-quality metrics against a fake, non-reasoning
    generator) — only `generation`/`retrieval` mode payloads do."""
    if not r.generation or "score" not in r.generation:
        return True
    return all(r.generation["score"].get(f, True) for f in ("citation_correct", "citation_complete", "forbidden_absent"))


def _failure_section(report: RunReport) -> list[str]:
    failures = [
        r for r in report.case_results
        if not r.status_ok
        or r.security_violation_count > 0
        or not _generation_quality_clean(r)
    ]
    if not failures:
        return ["--- Failure analysis ---", "  (no failures)"]

    lines = [f"--- Failure analysis ({len(failures)} case(s)) ---"]
    for r in failures:
        lines.append(f"[{r.case_id}] category={r.category} persona={r.persona} account={r.account_slug}")
        lines.append(f"    status: expected_ok={r.status_ok} actual={r.status_actual}")
        lines.append(f"    security_violations={r.security_violation_count} ({r.security})")
        if r.generation is not None:
            if "score" in r.generation:
                lines.append(f"    generation.score={r.generation['score']}")
            else:
                lines.append(f"    generation.context_citation_ids={r.generation.get('context_citation_ids')}")
                lines.append(f"    generation.context_commitment_ids={r.generation.get('context_commitment_ids')}")
            lines.append(f"    cited_stable_ids={r.generation.get('cited_stable_ids')}")
        if r.note_flags:
            lines.append(f"    flags={r.note_flags}")
        lines.append(f"    failure_category=UNCLASSIFIED — see docs/evaluation.md for manual triage")
    return lines
