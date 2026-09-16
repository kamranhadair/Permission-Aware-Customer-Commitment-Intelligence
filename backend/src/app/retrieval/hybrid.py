"""Reciprocal Rank Fusion — a pure function, no DB access, so merge
determinism (fixed ranks in -> fixed order out) is directly unit-testable
without a database.

RRF over weighted score normalization: lexical (ts_rank) and vector
(cosine distance) scores are on incomparable scales, and normalizing them
(min-max/z-score) is unstable for small candidate sets (division by zero
when every score ties, which is common at prototype scale). RRF only needs
ranks, which are always well-defined, and a chunk absent from a channel
simply contributes 0 rather than needing an arbitrary default score.
"""

from __future__ import annotations

from app.retrieval.types import LexicalCandidate, MergedTraceEntry, VectorCandidate

DEFAULT_K = 60
DEFAULT_LIMIT = 10


def reciprocal_rank_fusion(
    lexical: list[LexicalCandidate],
    vector: list[VectorCandidate],
    k: int = DEFAULT_K,
    limit: int = DEFAULT_LIMIT,
) -> list[MergedTraceEntry]:
    lexical_ranks: dict[int, int] = {c.chunk_id: c.rank for c in lexical}
    vector_ranks: dict[int, int] = {c.chunk_id: c.rank for c in vector}

    chunk_ids = set(lexical_ranks) | set(vector_ranks)
    entries = []
    for chunk_id in chunk_ids:
        lexical_rank = lexical_ranks.get(chunk_id)
        vector_rank = vector_ranks.get(chunk_id)
        score = 0.0
        if lexical_rank is not None:
            score += 1.0 / (k + lexical_rank)
        if vector_rank is not None:
            score += 1.0 / (k + vector_rank)
        entries.append(
            MergedTraceEntry(
                chunk_id=chunk_id, hybrid_score=score, lexical_rank=lexical_rank, vector_rank=vector_rank
            )
        )

    entries.sort(key=lambda e: (-e.hybrid_score, e.chunk_id))
    return entries[:limit]
