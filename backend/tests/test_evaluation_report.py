"""Regression test for a real bug: `report.render()` crashed with a
KeyError on any --mode security run, because `_failure_section` assumed
every `CaseResult.generation` payload had a "score" key — true for
`generation`/`retrieval` mode payloads, never true for `security` mode's
structural-only payload (see `_score_security_generation_case`, which never
computes answer-quality scores against a fake, non-reasoning generator).
Caught by actually running `python -m app.evaluation.run --mode security`
end to end, not just by unit-testing the scoring functions in isolation.
"""

from __future__ import annotations

from app.evaluation import report
from app.evaluation.runner import CaseResult, RunReport


def _security_style_case(case_id: str, security_violation_count: int = 0) -> CaseResult:
    return CaseResult(
        case_id=case_id, category="direct_lookup", persona="alice", account_slug="acme-corp", mode="security",
        status_actual="answered", status_ok=True,
        security={"unauthorized_citations": 0}, security_violation_count=security_violation_count,
        generation={
            "status": "answered",
            "context_citation_ids": ["E1"],
            "context_commitment_ids": [],
            "cited_stable_ids": [("call", "CALL-2001")],
        },
        manual_review=None,
    )


def test_render_does_not_crash_on_a_security_mode_generation_payload():
    run_report = RunReport(
        mode="security",
        timestamp="2026-01-01T00:00:00+00:00",
        case_results=[_security_style_case("dl-01")],
        freshness_results=[],
        automated_security_all_clear=True,
        manual_security_review_status="not_required",
        overall_security_status="passed",
    )
    rendered = report.render(run_report)
    assert "(no failures)" in rendered


def test_render_still_reports_a_security_mode_case_with_violations_as_a_failure():
    run_report = RunReport(
        mode="security",
        timestamp="2026-01-01T00:00:00+00:00",
        case_results=[_security_style_case("dl-01", security_violation_count=1)],
        freshness_results=[],
        automated_security_all_clear=False,
        manual_security_review_status="not_required",
        overall_security_status="failed",
    )
    rendered = report.render(run_report)
    assert "dl-01" in rendered
    assert "context_citation_ids" in rendered
    assert "(no failures)" not in rendered
