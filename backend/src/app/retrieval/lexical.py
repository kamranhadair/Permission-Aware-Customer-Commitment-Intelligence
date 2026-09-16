"""Permission-scoped PostgreSQL full-text search. `document_ids` comes from
the same resolver function every other permission-aware query goes
through — no separate/subtly-different ACL predicate lives here."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk
from app.permissions.resolver import UserContext, get_permitted_document_ids
from app.retrieval.types import LexicalCandidate

DEFAULT_LIMIT = 20


def lexical_search(
    db: Session,
    user_ctx: UserContext,
    query: str,
    account_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[LexicalCandidate]:
    document_ids = get_permitted_document_ids(db, user_ctx, account_id)
    if not document_ids:
        return []

    tsvector = func.to_tsvector("english", Chunk.content)
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(tsvector, tsquery).label("score")

    stmt = (
        select(Chunk.id, Chunk.document_id, rank)
        .where(Chunk.document_id.in_(document_ids))
        .where(tsvector.op("@@")(tsquery))
        .order_by(rank.desc(), Chunk.id.asc())
        .limit(limit)
    )

    return [
        LexicalCandidate(chunk_id=row.id, document_id=row.document_id, rank=idx, score=row.score)
        for idx, row in enumerate(db.execute(stmt), start=1)
    ]
