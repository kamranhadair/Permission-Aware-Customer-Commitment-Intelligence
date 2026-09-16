"""Unit tests for `--resume`'s completed/retryable state distinction
(Milestone 6 follow-up design item 6). Pure function, no DB, no network:
a persisted record's `status_actual` alone determines whether the next
`--resume` skips it (a real, usable result) or retries it (the provider
request never completed, or completed but produced nothing gracious to
show for it).
"""

from __future__ import annotations

from app.evaluation.runner import _resumable_completed_results


def _record(case_id: str, status_actual: str, **extra) -> dict:
    return {"case_id": case_id, "status_actual": status_actual, **extra}


def test_answered_case_is_treated_as_completed():
    result = _resumable_completed_results([_record("g1", "answered")])
    assert "g1" in result


def test_insufficient_evidence_case_is_treated_as_completed():
    result = _resumable_completed_results([_record("g2", "insufficient_evidence")])
    assert "g2" in result


def test_account_not_visible_case_is_treated_as_completed():
    result = _resumable_completed_results([_record("g3", "account_not_visible")])
    assert "g3" in result


def test_generation_failure_case_is_retryable_not_completed():
    """Covers both shapes of generation_failure — a provider/network/quota
    error (the request never completed) and an all-claims-invalid response
    (the request completed but produced nothing usable) — the persisted
    status_actual is identical ("generation_failure") for both, and in
    either case the case must be retried on the next --resume rather than
    silently treated as done."""
    result = _resumable_completed_results([_record("g4", "generation_failure")])
    assert "g4" not in result


def test_case_pending_manual_review_is_still_completed_and_not_retried():
    """A case that finished (real claims/citations persisted) but is
    waiting on a human verdict for unauthorized_fact_emitted/
    hidden_conflict_leakage must NOT be re-sent to the provider — its
    persisted result is kept, only its manual_review field changes later
    via --review-case-id."""
    result = _resumable_completed_results([
        _record("g5", "answered", manual_review={"unauthorized_fact_emitted": "pending_review", "hidden_conflict_leakage": "pending_review"}),
    ])
    assert "g5" in result
    assert result["g5"]["manual_review"]["unauthorized_fact_emitted"] == "pending_review"


def test_mixed_batch_only_completed_ones_are_skipped():
    persisted = [
        _record("g1", "answered"),
        _record("g2", "generation_failure"),
        _record("g3", "insufficient_evidence"),
        _record("g4", "generation_failure"),
        _record("g5", "account_not_visible"),
    ]
    result = _resumable_completed_results(persisted)
    assert set(result) == {"g1", "g3", "g5"}


def test_empty_persisted_list_resumes_everything():
    assert _resumable_completed_results([]) == {}
