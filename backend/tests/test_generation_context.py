"""Pure unit tests for app/generation/context.py — no DB. Both inputs
(retrieval hits, commitments) are constructed directly as already
permission-scoped data, exactly as the real resolver/retrieval functions
would hand them off; context.py itself does zero ACL logic, so these tests
only need to prove its ordering/bounding/linkage behavior."""

from datetime import date, datetime, timezone

from app.generation.context import (
    MAX_COMMITMENT_CONTEXT_BLOCKS,
    MAX_EVIDENCE_CONTEXT,
    RETRIEVAL_CONTEXT_LIMIT,
    build_context,
)
from app.permissions.resolver import ChunkView, CommitmentWithEvidence
from app.retrieval.types import RetrievalHit


def _hit(chunk_id: int, occurred_at: datetime, content: str = "content") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        document_id=100 + chunk_id,
        account_id=1,
        source="call",
        title=f"doc-{chunk_id}",
        content=content,
        occurred_at=occurred_at,
        lexical_rank=1,
        vector_rank=1,
        hybrid_score=1.0,
    )


def _chunk_view(chunk_id: int, occurred_at: datetime, content: str = "content") -> ChunkView:
    return ChunkView(
        id=chunk_id,
        document_id=200 + chunk_id,
        source="slack",
        title=f"chunk-{chunk_id}",
        sensitivity="internal",
        occurred_at=occurred_at,
        content=content,
    )


def _commitment(
    commitment_id: int,
    supporting: list[ChunkView],
    conflicting: list[ChunkView] | None = None,
    authority: str = "product_approved",
    promise_date: date = date(2026, 1, 1),
) -> CommitmentWithEvidence:
    return CommitmentWithEvidence(
        id=commitment_id,
        statement=f"statement-{commitment_id}",
        promised_by="Someone",
        promise_date=promise_date,
        delivery_date=None,
        authority=authority,
        status="on_track",
        supporting=supporting,
        conflicting=conflicting or [],
    )


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_retrieval_hits_keep_hybrid_rank_order_not_reordered_by_time():
    hits = [
        _hit(1, T0),
        _hit(2, T0.replace(year=2030)),  # newest, but ranked second by hybrid
        _hit(3, T0.replace(year=2020)),  # oldest, ranked third by hybrid
    ]
    context = build_context(hits, [])
    assert [c.chunk_id for c in context.evidence] == [1, 2, 3]
    assert [c.citation_id for c in context.evidence] == ["E1", "E2", "E3"]


def test_commitment_evidence_appended_after_retrieval_newest_first_deterministic():
    hits = [_hit(1, T0)]
    older = _chunk_view(2, T0.replace(year=2020))
    newer = _chunk_view(3, T0.replace(year=2025))
    same_time_a = _chunk_view(4, T0.replace(year=2025))  # tie on occurred_at with `newer`
    commitments = [_commitment(1, supporting=[older, newer, same_time_a])]

    context = build_context(hits, commitments)

    # E1 = retrieval hit; extras ordered occurred_at DESC, chunk_id ASC on ties.
    assert [c.chunk_id for c in context.evidence] == [1, 3, 4, 2]


def test_max_evidence_context_cap_never_truncates_retrieval_hits():
    hits = [_hit(i, T0) for i in range(1, RETRIEVAL_CONTEXT_LIMIT + 1)]  # exactly 8
    extras = [_chunk_view(100 + i, T0.replace(year=2020 + i)) for i in range(5)]  # 5 candidates, only 2 fit
    commitments = [_commitment(1, supporting=extras)]

    context = build_context(hits, commitments)

    assert len(context.evidence) == MAX_EVIDENCE_CONTEXT
    retrieval_ids = {c.chunk_id for c in hits}
    assert retrieval_ids <= {c.chunk_id for c in context.evidence}  # all 8 retrieval hits survive
    # The 2 surviving extras are the newest two (2024, 2023 in that construction).
    extra_ids_in_context = [c.chunk_id for c in context.evidence if c.chunk_id not in retrieval_ids]
    assert extra_ids_in_context == [104, 103]


def test_max_commitment_context_blocks_cap():
    hits = [_hit(1, T0)]
    commitments = [_commitment(i, supporting=[_chunk_view(1, T0)], promise_date=date(2026, 1, i)) for i in range(1, 13)]

    context = build_context(hits, commitments)

    assert len(context.commitments) == MAX_COMMITMENT_CONTEXT_BLOCKS
    # Ordered promise_date DESC, id ASC -> commitment 12 (Jan 12) first.
    assert context.commitments[0].commitment_id == 12


def test_commitment_with_zero_surviving_support_after_cap_is_omitted():
    """Regression for the constraint: a commitment may be permission-visible
    in the DB but still omitted from THIS request's context if none of its
    supporting evidence survived the MAX_EVIDENCE_CONTEXT bound."""
    hits = [_hit(i, T0) for i in range(1, RETRIEVAL_CONTEXT_LIMIT + 1)]  # fills E1..E8

    old_support = _chunk_view(901, T0.replace(year=2019))  # oldest extra -> gets truncated out
    newer_a = _chunk_view(902, T0.replace(year=2024))
    newer_b = _chunk_view(903, T0.replace(year=2025))

    commitment_x = _commitment(1, supporting=[old_support], authority="product_target")
    commitment_y = _commitment(2, supporting=[newer_a, newer_b], authority="product_approved")

    context = build_context(hits, [commitment_x, commitment_y])

    assert len(context.evidence) == MAX_EVIDENCE_CONTEXT
    assert 901 not in {c.chunk_id for c in context.evidence}  # truncated out
    commitment_ids_present = {c.commitment_id for c in context.commitments}
    assert 1 not in commitment_ids_present  # its only support was truncated -> block omitted
    assert 2 in commitment_ids_present


def test_conflicting_evidence_may_be_empty_but_supporting_may_not():
    hits: list[RetrievalHit] = []
    supported_only = _commitment(1, supporting=[_chunk_view(1, T0)], conflicting=[])
    context = build_context(hits, [supported_only])
    assert len(context.commitments) == 1
    assert context.commitments[0].supporting_citation_ids == ["E1"]
    assert context.commitments[0].conflicting_citation_ids == []


def test_cross_commitment_evidence_isolation():
    chunk_a = _chunk_view(1, T0)
    chunk_b = _chunk_view(2, T0)
    commitment_a = _commitment(1, supporting=[chunk_a], authority="sales_unapproved")
    commitment_b = _commitment(2, supporting=[chunk_b], authority="product_approved")

    context = build_context([], [commitment_a, commitment_b])

    by_id = {c.commitment_id: c for c in context.commitments}
    assert by_id[1].supporting_citation_ids == ["E1"]
    assert by_id[2].supporting_citation_ids == ["E2"]
    # Neither commitment's supporting list leaks the other's evidence.
    assert "E2" not in by_id[1].supporting_citation_ids
    assert "E1" not in by_id[2].supporting_citation_ids
