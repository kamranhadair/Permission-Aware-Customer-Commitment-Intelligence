"""Pure unit tests for reciprocal_rank_fusion — no DB. These prove merge
determinism and the RRF math in isolation from any permission concern
(that's proven separately in test_retrieval_lexical/vector/service.py by
showing every candidate list fed into this function already came from a
permission-scoped query)."""

from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.types import LexicalCandidate, VectorCandidate


def _lex(chunk_id: int, rank: int) -> LexicalCandidate:
    return LexicalCandidate(chunk_id=chunk_id, document_id=1, rank=rank, score=1.0 / rank)


def _vec(chunk_id: int, rank: int) -> VectorCandidate:
    return VectorCandidate(chunk_id=chunk_id, document_id=1, rank=rank, score=float(rank))


def test_lexical_only_hit_survives_hybrid_merge():
    merged = reciprocal_rank_fusion([_lex(1, 1)], [], limit=10)
    assert [e.chunk_id for e in merged] == [1]
    assert merged[0].lexical_rank == 1
    assert merged[0].vector_rank is None


def test_vector_only_hit_survives_hybrid_merge():
    merged = reciprocal_rank_fusion([], [_vec(2, 1)], limit=10)
    assert [e.chunk_id for e in merged] == [2]
    assert merged[0].lexical_rank is None
    assert merged[0].vector_rank == 1


def test_both_channel_hit_gets_combined_rank_higher_than_either_alone():
    lexical = [_lex(1, 1), _lex(2, 2)]
    vector = [_vec(2, 1), _vec(3, 2)]
    merged = reciprocal_rank_fusion(lexical, vector, k=60, limit=10)

    by_id = {e.chunk_id: e for e in merged}
    # chunk 2 appears in both channels; its score is the sum of both
    # reciprocal ranks, which must exceed any single-channel score.
    expected_combined = 1 / (60 + 2) + 1 / (60 + 1)
    assert by_id[2].hybrid_score == expected_combined
    assert by_id[2].hybrid_score > by_id[1].hybrid_score
    assert by_id[2].hybrid_score > by_id[3].hybrid_score


def test_every_merged_result_traceable_to_a_candidate_list():
    lexical = [_lex(1, 1), _lex(2, 2)]
    vector = [_vec(3, 1)]
    merged = reciprocal_rank_fusion(lexical, vector, limit=10)
    merged_ids = {e.chunk_id for e in merged}
    candidate_ids = {c.chunk_id for c in lexical} | {c.chunk_id for c in vector}
    assert merged_ids <= candidate_ids


def test_hybrid_order_is_deterministic_for_fixed_ranks_and_scores():
    lexical = [_lex(1, 1), _lex(2, 2), _lex(3, 3)]
    vector = [_vec(3, 1), _vec(1, 2)]

    first = reciprocal_rank_fusion(lexical, vector, limit=10)
    second = reciprocal_rank_fusion(lexical, vector, limit=10)
    assert [e.chunk_id for e in first] == [e.chunk_id for e in second]


def test_tied_hybrid_scores_break_ties_by_chunk_id_ascending():
    # Two chunks with identical single-channel rank produce identical scores.
    lexical = [_lex(5, 1), _lex(2, 1)]
    merged = reciprocal_rank_fusion(lexical, [], limit=10)
    assert merged[0].hybrid_score == merged[1].hybrid_score
    assert [e.chunk_id for e in merged] == [2, 5]


def test_limit_truncates_merged_results():
    lexical = [_lex(i, i) for i in range(1, 6)]
    merged = reciprocal_rank_fusion(lexical, [], limit=3)
    assert len(merged) == 3
    assert [e.chunk_id for e in merged] == [1, 2, 3]
