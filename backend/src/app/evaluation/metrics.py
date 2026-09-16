"""Deterministic, automatable metrics only (Milestone 6 design sections 4/9).

Retrieval metrics (Recall@5, Recall@10, MRR) are document-level, matching
`stable_ids.py`'s document-level identity scheme — a case counts as a hit
at rank r if the document a ranked chunk belongs to is in the expected set,
using each document's FIRST occurrence rank.

Generation metrics reduce to citation-set checks wherever Milestone 5's own
validator already makes the underlying error structurally impossible (see
`app/generation/validation.py`) — authority and conflict "correctness" are
not separately computed mechanisms, they are the same citation-set checks
under a different name, exactly as documented in Milestone 5's evaluate.py
docstring and carried forward here rather than reinvented.
"""

from __future__ import annotations

from dataclasses import dataclass


def _first_occurrence_doc_ranks(ranked_chunk_ids: list[int], chunk_to_doc: dict[int, int]) -> list[int]:
    seen: set[int] = set()
    ordered_docs: list[int] = []
    for chunk_id in ranked_chunk_ids:
        doc_id = chunk_to_doc.get(chunk_id)
        if doc_id is None or doc_id in seen:
            continue
        seen.add(doc_id)
        ordered_docs.append(doc_id)
    return ordered_docs


def recall_at_k(expected_doc_ids: set[int], ranked_chunk_ids: list[int], chunk_to_doc: dict[int, int], k: int) -> float:
    ranked_docs = _first_occurrence_doc_ranks(ranked_chunk_ids, chunk_to_doc)
    if not expected_doc_ids:
        # A permission-exclusion / no-evidence-exists case: correct behavior is zero results.
        return 1.0 if not ranked_docs[:k] else 0.0
    hit = len(expected_doc_ids & set(ranked_docs[:k]))
    return hit / len(expected_doc_ids)


def mrr(expected_doc_ids: set[int], ranked_chunk_ids: list[int], chunk_to_doc: dict[int, int]) -> float:
    ranked_docs = _first_occurrence_doc_ranks(ranked_chunk_ids, chunk_to_doc)
    for idx, doc_id in enumerate(ranked_docs, start=1):
        if doc_id in expected_doc_ids:
            return 1.0 / idx
    return 0.0


@dataclass(frozen=True)
class GenerationScore:
    status_correct: bool
    citation_correct: bool  # cited document ids are a subset of expected (when expected is non-empty)
    citation_complete: bool  # expected document ids are a subset of cited (when expected is non-empty)
    forbidden_absent: bool  # no forbidden document id was ever cited
    temporal_correct: bool | None  # None when the case has no temporal expectation
    authority_correct: bool | None  # None when the case has no authority expectation


def score_generation(
    *,
    actual_status: str,
    acceptable_statuses: set[str],
    cited_doc_ids: set[int],
    expected_doc_ids: set[int],
    forbidden_doc_ids: set[int],
    expected_temporal_doc_id: int | None,
    expected_authority: str | None,
    actual_authority_for_expected_evidence: str | None,
) -> GenerationScore:
    citation_correct = cited_doc_ids <= expected_doc_ids if expected_doc_ids else True
    citation_complete = expected_doc_ids <= cited_doc_ids if expected_doc_ids else True
    forbidden_absent = not (cited_doc_ids & forbidden_doc_ids)

    temporal_correct = None
    if expected_temporal_doc_id is not None:
        temporal_correct = expected_temporal_doc_id in cited_doc_ids

    authority_correct = None
    if expected_authority is not None:
        authority_correct = actual_authority_for_expected_evidence == expected_authority

    return GenerationScore(
        status_correct=actual_status in acceptable_statuses,
        citation_correct=citation_correct,
        citation_complete=citation_complete,
        forbidden_absent=forbidden_absent,
        temporal_correct=temporal_correct,
        authority_correct=authority_correct,
    )
