"""Unit tests for `runner._compute_security_status` — the three-way
security-status semantics (Milestone 6 follow-up design). No DB needed:
this is a pure function over plain dicts shaped like `CaseResult.to_dict()`
and a freshness-sequence result.
"""

from __future__ import annotations

from app.evaluation.runner import _compute_security_status


def _case(security_violation_count: int = 0, manual_review: dict | None = None) -> dict:
    return {"security_violation_count": security_violation_count, "manual_review": manual_review}


def _freshness_step(security_violations: int = 0, forbidden_absent: bool = True) -> dict:
    return {"security_violations": security_violations, "forbidden_absent": forbidden_absent}


def test_all_structural_cases_clean_plus_freshness_violation_fails_automated():
    cases = [_case(), _case()]
    freshness = [{"sequence_id": "seq-1", "steps": [_freshness_step(), _freshness_step(security_violations=1)]}]

    automated, manual, overall = _compute_security_status(cases, freshness)

    assert automated is False
    assert manual == "not_required"
    assert overall == "failed"


def test_freshness_forbidden_present_also_fails_automated_even_with_zero_violation_count():
    cases = [_case()]
    freshness = [{"sequence_id": "seq-1", "steps": [_freshness_step(security_violations=0, forbidden_absent=False)]}]

    automated, manual, overall = _compute_security_status(cases, freshness)

    assert automated is False
    assert overall == "failed"


def test_automated_clean_plus_one_pending_manual_gate_is_pending_review():
    cases = [
        _case(),
        _case(manual_review={"unauthorized_fact_emitted": "pass", "hidden_conflict_leakage": "pending_review"}),
    ]

    automated, manual, overall = _compute_security_status(cases, [])

    assert automated is True
    assert manual == "pending"
    assert overall == "pending_review"


def test_automated_clean_plus_reviewed_manual_gate_failing_is_overall_failed():
    cases = [
        _case(manual_review={"unauthorized_fact_emitted": "fail", "hidden_conflict_leakage": "pass"}),
    ]

    automated, manual, overall = _compute_security_status(cases, [])

    assert automated is True
    assert manual == "failed"
    assert overall == "failed"


def test_all_required_gates_pass_is_overall_passed():
    cases = [
        _case(),
        _case(manual_review={"unauthorized_fact_emitted": "pass", "hidden_conflict_leakage": "pass"}),
    ]
    freshness = [{"sequence_id": "seq-1", "steps": [_freshness_step(), _freshness_step()]}]

    automated, manual, overall = _compute_security_status(cases, freshness)

    assert automated is True
    assert manual == "passed"
    assert overall == "passed"


def test_no_manual_review_cases_at_all_is_not_required():
    cases = [_case(), _case()]

    automated, manual, overall = _compute_security_status(cases, [])

    assert manual == "not_required"
    assert overall == "passed"


def test_notes_key_inside_manual_review_is_ignored_not_treated_as_a_gate_value():
    cases = [
        _case(manual_review={
            "unauthorized_fact_emitted": "pass",
            "hidden_conflict_leakage": "pass",
            "notes": {"unauthorized_fact_emitted": "reviewer comment, not a gate verdict"},
        }),
    ]

    automated, manual, overall = _compute_security_status(cases, [])

    assert manual == "passed"
    assert overall == "passed"
