"""Pure-function unit tests for app/evaluation/metrics.py — no DB, no
network. Recall/MRR are document-level (Milestone 6 design section 5): a
hit counts at a document's FIRST occurrence rank among its chunks.
"""

from __future__ import annotations

from app.evaluation.metrics import mrr, recall_at_k, score_generation


def test_recall_at_k_document_level_first_occurrence():
    # doc 10 appears via chunks 1 and 2; doc 20 via chunk 3.
    chunk_to_doc = {1: 10, 2: 10, 3: 20}
    ranked = [2, 1, 3]  # doc 10 first seen at rank 1, doc 20 at rank 3
    assert recall_at_k({10}, ranked, chunk_to_doc, k=1) == 1.0
    assert recall_at_k({20}, ranked, chunk_to_doc, k=1) == 0.0
    assert recall_at_k({20}, ranked, chunk_to_doc, k=3) == 1.0


def test_recall_at_k_partial_credit_across_multiple_expected_docs():
    chunk_to_doc = {1: 10, 2: 20}
    assert recall_at_k({10, 20}, [1], chunk_to_doc, k=5) == 0.5


def test_recall_at_k_empty_expected_scores_one_only_if_nothing_returned():
    assert recall_at_k(set(), [], {}, k=5) == 1.0
    assert recall_at_k(set(), [1], {1: 10}, k=5) == 0.0


def test_mrr_first_hit_rank():
    chunk_to_doc = {1: 10, 2: 20, 3: 30}
    assert mrr({30}, [1, 2, 3], chunk_to_doc) == 1 / 3
    assert mrr({999}, [1, 2, 3], chunk_to_doc) == 0.0


def test_score_generation_citation_correct_and_complete():
    score = score_generation(
        actual_status="answered",
        acceptable_statuses={"answered"},
        cited_doc_ids={1, 2},
        expected_doc_ids={1, 2},
        forbidden_doc_ids=set(),
        expected_temporal_doc_id=None,
        expected_authority=None,
        actual_authority_for_expected_evidence=None,
    )
    assert score.status_correct
    assert score.citation_correct
    assert score.citation_complete
    assert score.forbidden_absent


def test_score_generation_citation_incomplete_when_expected_not_cited():
    score = score_generation(
        actual_status="answered",
        acceptable_statuses={"answered"},
        cited_doc_ids=set(),
        expected_doc_ids={1},
        forbidden_doc_ids=set(),
        expected_temporal_doc_id=None,
        expected_authority=None,
        actual_authority_for_expected_evidence=None,
    )
    assert not score.citation_complete
    assert score.citation_correct  # nothing wrong was cited, even though nothing required was either


def test_score_generation_forbidden_present_fails_gate():
    score = score_generation(
        actual_status="answered",
        acceptable_statuses={"answered"},
        cited_doc_ids={1, 99},
        expected_doc_ids={1},
        forbidden_doc_ids={99},
        expected_temporal_doc_id=None,
        expected_authority=None,
        actual_authority_for_expected_evidence=None,
    )
    assert not score.forbidden_absent
    assert not score.citation_correct  # 99 is not in expected_doc_ids either


def test_score_generation_authority_mismatch():
    score = score_generation(
        actual_status="answered",
        acceptable_statuses={"answered"},
        cited_doc_ids={1},
        expected_doc_ids={1},
        forbidden_doc_ids=set(),
        expected_temporal_doc_id=None,
        expected_authority="contractual",
        actual_authority_for_expected_evidence="product_target",
    )
    assert score.authority_correct is False


def test_score_generation_temporal_precedence_not_cited():
    score = score_generation(
        actual_status="answered",
        acceptable_statuses={"answered"},
        cited_doc_ids={1},
        expected_doc_ids={1, 2},
        forbidden_doc_ids=set(),
        expected_temporal_doc_id=2,
        expected_authority=None,
        actual_authority_for_expected_evidence=None,
    )
    assert score.temporal_correct is False
