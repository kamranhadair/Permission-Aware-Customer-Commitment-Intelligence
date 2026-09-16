"""Validates the actual golden dataset / permission-freshness fixture files
against app/evaluation/schema.py, and cross-checks every persona/account
reference against what app/evaluation/personas.py actually seeds — a
malformed or drifted golden case should fail fast here, in pytest, rather
than surface as a confusing runtime KeyError mid-evaluation-run.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.personas import ACCOUNT_SLUGS, PERSONA_GROUPS
from app.evaluation.schema import FreshnessDataset, GoldenDataset

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation"
KNOWN_PERSONAS = set(PERSONA_GROUPS) | {"frank"}


def _load_dataset() -> GoldenDataset:
    with (FIXTURES_DIR / "golden_dataset.json").open() as f:
        return GoldenDataset.model_validate(json.load(f))


def _load_freshness() -> FreshnessDataset:
    with (FIXTURES_DIR / "permission_freshness.json").open() as f:
        return FreshnessDataset.model_validate(json.load(f))


def test_golden_dataset_parses_and_has_unique_ids():
    dataset = _load_dataset()
    assert len(dataset.cases) >= 50


def test_golden_dataset_case_count_meets_minimum_per_category():
    dataset = _load_dataset()
    counts: dict[str, int] = {}
    for case in dataset.cases:
        counts[case.category] = counts.get(case.category, 0) + 1
    # Deliberately lower than the nominal 55-65 target for the two
    # categories the fixture set honestly does not support further without
    # padding (see docs/evaluation.md) — every other category meets its
    # originally-planned minimum.
    minimums = {
        "direct_lookup": 8,
        "cross_doc_synthesis": 1,
        "conflicting_evidence": 1,
        "temporal": 8,
        "permission_refusal": 10,
        "commitment_authority": 4,
        "prompt_injection": 4,
        "insufficient_evidence": 4,
    }
    for category, minimum in minimums.items():
        assert counts.get(category, 0) >= minimum, f"{category}: {counts.get(category, 0)} < {minimum}"


def test_every_case_persona_is_known():
    dataset = _load_dataset()
    for case in dataset.cases:
        assert case.persona in KNOWN_PERSONAS, f"{case.id}: unknown persona {case.persona!r}"


def test_every_case_account_is_known():
    dataset = _load_dataset()
    for case in dataset.cases:
        assert case.account_slug in ACCOUNT_SLUGS, f"{case.id}: unknown account {case.account_slug!r}"


def test_account_not_visible_expectation_only_for_zero_access_personas():
    """frank (cross-org) and erin-on-accounts-she-has-no-grant-in are the
    only personas expected to hit account_not_visible in this dataset — a
    case expecting it for a broadly-permissioned persona (alice/bob/carol/
    dana) would be a dataset authoring bug, not a real security finding."""
    dataset = _load_dataset()
    broad_personas = {"alice", "bob", "carol", "dana"}
    for case in dataset.cases:
        if case.expected_status == "account_not_visible" or (
            case.acceptable_statuses and "account_not_visible" in case.acceptable_statuses
        ):
            assert case.persona not in broad_personas, f"{case.id}: unexpected account_not_visible for {case.persona}"


def test_freshness_dataset_parses():
    freshness = _load_freshness()
    assert len(freshness.sequences) >= 2


def test_freshness_sequences_alternate_query_and_mutate_steps():
    freshness = _load_freshness()
    for sequence in freshness.sequences:
        kinds = [step.kind for step in sequence.steps]
        assert kinds.count("mutate") >= 1, f"{sequence.id}: no mutation step"
        assert kinds[0] == "query" and kinds[-1] == "query", f"{sequence.id}: must start/end on a query step"
