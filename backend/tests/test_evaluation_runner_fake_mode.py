"""The full-dataset architecture/security regression (Milestone 6 design
section 14) — runs every golden case and every permission-freshness
sequence through `security` mode (FakeEmbeddingProvider + FakeAnswerGenerator,
no network) inside the pytest `db` fixture's SAVEPOINT-backed session, so it
never leaves committed rows in TEST_DATABASE_URL. This is the one test that
exercises the real fixtures/evaluation/*.json content end to end; every
other test_evaluation_*.py file tests one piece of the runner in isolation.
"""

from __future__ import annotations

from app.evaluation import runner


def test_security_mode_full_dataset_all_clear(db):
    report = runner.run(mode="security", db=db)

    assert report.automated_security_all_clear, [
        (r.case_id, r.security) for r in report.case_results if r.security_violation_count > 0
    ]
    assert report.manual_security_review_status == "not_required", (
        "security mode must never pretend to prove the two semantic model-output gates"
    )
    assert report.overall_security_status == "passed"
    assert len(report.case_results) >= 50

    account_not_visible_failures = [
        r.case_id for r in report.case_results if not r.status_ok
    ]
    assert not account_not_visible_failures, account_not_visible_failures

    assert report.freshness_results
    for seq in report.freshness_results:
        for step in seq["steps"]:
            assert step["status_ok"], (seq["sequence_id"], step)
            assert step["forbidden_absent"], (seq["sequence_id"], step)
            assert step["security_violations"] == 0, (seq["sequence_id"], step)


def test_security_mode_respects_limit_and_case_id(db):
    report = runner.run(mode="security", case_id="dl-01", db=db)
    assert len(report.case_results) == 1
    assert report.case_results[0].case_id == "dl-01"
