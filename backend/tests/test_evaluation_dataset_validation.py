"""Proves the golden dataset's evaluator-privileged claims (`expected_evidence`,
`forbidden_evidence`) are validated against the real seeded database rather
than trusted "by construction" (Milestone 6 follow-up design item 4).
"""

from __future__ import annotations

import pytest

from app.evaluation import personas as personas_module
from app.evaluation.dataset_validation import validate_freshness_dataset, validate_golden_dataset
from app.evaluation.fixtures_loader import ingest_all_fixtures, seed_commitments
from app.evaluation.runner import _load_dataset, _load_freshness
from app.evaluation.schema import GoldenCase, GoldenDataset, StableEvidenceRef


def _seed(db) -> personas_module.EvalSeed:
    seed = personas_module.seed(db)
    ingest_all_fixtures(db, seed.org.id)
    seed_commitments(db, seed.accounts)
    return seed


def test_real_golden_dataset_validates_cleanly(db):
    seed = _seed(db)
    errors = validate_golden_dataset(db, seed, _load_dataset())
    assert errors == [], errors


def test_real_freshness_dataset_validates_cleanly(db):
    seed = _seed(db)
    errors = validate_freshness_dataset(db, seed, _load_freshness())
    assert errors == [], errors


def test_expected_evidence_that_does_not_resolve_is_reported(db):
    seed = _seed(db)
    bad_case = GoldenCase(
        id="bad-01", category="direct_lookup", persona="alice", account_slug="acme-corp",
        query="q", expected_status="answered",
        expected_evidence=[StableEvidenceRef(source="support", external_id="TICK-DOES-NOT-EXIST")],
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    assert len(errors) == 1
    assert "bad-01" in errors[0]
    assert "TICK-DOES-NOT-EXIST" in errors[0]


def test_forbidden_evidence_that_does_not_resolve_is_reported(db):
    seed = _seed(db)
    bad_case = GoldenCase(
        id="bad-02", category="permission_refusal", persona="alice", account_slug="acme-corp",
        query="q", expected_status="insufficient_evidence",
        forbidden_evidence=[StableEvidenceRef(source="support", external_id="TICK-DOES-NOT-EXIST")],
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    assert len(errors) == 1
    assert "bad-02" in errors[0]


def test_forbidden_evidence_that_is_actually_permitted_is_reported(db):
    seed = _seed(db)
    # TICK-1001 is a direct-user ACL grant to alice (see fixtures/support/tickets.json)
    # — genuinely permitted to her, so labeling it forbidden for alice is a dataset bug.
    bad_case = GoldenCase(
        id="bad-03", category="permission_refusal", persona="alice", account_slug="acme-corp",
        query="q", expected_status="insufficient_evidence",
        forbidden_evidence=[StableEvidenceRef(source="support", external_id="TICK-1001")],
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    assert len(errors) == 1
    assert "bad-03" in errors[0]
    assert "PERMITTED" in errors[0]


def test_forbidden_evidence_genuinely_outside_permitted_set_is_not_reported(db):
    seed = _seed(db)
    # C-ACME-INTERNAL is product/exec-only; alice (account-management) genuinely
    # cannot see it — a correctly-labeled forbidden_evidence case.
    good_case = GoldenCase(
        id="good-01", category="permission_refusal", persona="alice", account_slug="acme-corp",
        query="q", expected_status="insufficient_evidence",
        forbidden_evidence=[StableEvidenceRef(source="slack", external_id="C-ACME-INTERNAL:1722000000.0001")],
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[good_case]))
    assert errors == []


def test_expected_and_forbidden_overlap_is_reported(db):
    seed = _seed(db)
    bad_case = GoldenCase(
        id="bad-04", category="direct_lookup", persona="alice", account_slug="acme-corp",
        query="q", expected_status="answered",
        expected_evidence=[StableEvidenceRef(source="support", external_id="TICK-1001")],
        forbidden_evidence=[StableEvidenceRef(source="support", external_id="TICK-1001")],
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    # TICK-1001 is genuinely permitted to alice, so this case is doubly
    # malformed (overlap AND a mislabeled forbidden_evidence) — both are
    # correct, independent findings, not a single error.
    assert any("overlap" in e for e in errors), errors


def test_unknown_account_slug_is_reported(db):
    seed = _seed(db)
    bad_case = GoldenCase(
        id="bad-05", category="direct_lookup", persona="alice", account_slug="no-such-account",
        query="q", expected_status="answered",
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    assert len(errors) == 1
    assert "no-such-account" in errors[0]


def test_unknown_persona_is_reported(db):
    seed = _seed(db)
    bad_case = GoldenCase(
        id="bad-06", category="direct_lookup", persona="nobody", account_slug="acme-corp",
        query="q", expected_status="answered",
    )
    errors = validate_golden_dataset(db, seed, GoldenDataset(cases=[bad_case]))
    assert len(errors) == 1
    assert "nobody" in errors[0]


def test_malformed_dataset_makes_run_raise_before_scoring_any_case(db, monkeypatch):
    from app.evaluation import runner

    bad_case = GoldenCase(
        id="bad-07", category="direct_lookup", persona="alice", account_slug="acme-corp",
        query="q", expected_status="answered",
        expected_evidence=[StableEvidenceRef(source="support", external_id="TICK-DOES-NOT-EXIST")],
    )
    monkeypatch.setattr(runner, "_load_dataset", lambda: GoldenDataset(cases=[bad_case]))

    scoring_calls = []
    monkeypatch.setattr(
        runner, "_score_retrieval_case", lambda *a, **k: scoring_calls.append(1) or None
    )

    with pytest.raises(ValueError, match="bad-07"):
        runner.run(mode="security", db=db)

    assert scoring_calls == [], "no case should ever be scored when the dataset itself is malformed"
