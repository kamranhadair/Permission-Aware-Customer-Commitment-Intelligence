"""Permission-scoped pgvector cosine-similarity search. Same `document_ids`
resolver call as lexical.py — one shared ACL predicate for both channels.

Exact (brute-force) nearest-neighbor, deliberately: no HNSW/IVFFlat index
exists (see alembic/versions/0004_chunk_embeddings.py). The permission
predicate and `embedding IS NOT NULL` are evaluated in this query's WHERE
clause against literal rows, before ORDER BY/LIMIT ranks anything — there
is no approximate index traversal step that could ever surface an
unauthorized or unembedded row as a candidate.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk
from app.permissions.resolver import UserContext, get_permitted_document_ids
from app.retrieval.types import VectorCandidate

DEFAULT_LIMIT = 20


def vector_search(
    db: Session,
    user_ctx: UserContext,
    query_embedding: list[float],
    account_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[VectorCandidate]:
    document_ids = get_permitted_document_ids(db, user_ctx, account_id)
    if not document_ids:
        return []

    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(Chunk.id, Chunk.document_id, distance)
        .where(Chunk.document_id.in_(document_ids))
        .where(Chunk.embedding.is_not(None))
        .order_by(distance.asc(), Chunk.id.asc())
        .limit(limit)
    )

    return [
        VectorCandidate(chunk_id=row.id, document_id=row.document_id, rank=idx, score=row.distance)
        for idx, row in enumerate(db.execute(stmt), start=1)
    ]
