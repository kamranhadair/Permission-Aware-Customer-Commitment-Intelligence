"""The one retrieval boundary. `retrieve()` is the only thing routers (or
anything else) should call — it owns account-scope resolution, calling
both search channels, the hybrid merge, and building the trace.

Trace safety, by construction rather than by redaction: `lexical_search`
and `vector_search` only ever produce chunk ids already scoped by
`get_permitted_document_ids` (the same resolver function every other
permission-aware query in this codebase goes through). Nothing "filtered
out" is ever computed or held anywhere in this module, so there is no
redaction step whose omission could leak anything — every id that reaches
`RetrievalTrace` was already authorized before this function ran.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Chunk, SourceDocument
from app.permissions.resolver import UserContext, get_visible_account
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.hybrid import DEFAULT_K, reciprocal_rank_fusion
from app.retrieval.lexical import DEFAULT_LIMIT as LEXICAL_DEFAULT_LIMIT
from app.retrieval.lexical import lexical_search
from app.retrieval.types import RetrievalHit, RetrievalResult, RetrievalTrace, TraceCandidate
from app.retrieval.vector import DEFAULT_LIMIT as VECTOR_DEFAULT_LIMIT
from app.retrieval.vector import vector_search

DEFAULT_RESULT_LIMIT = 10


def retrieve(
    db: Session,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    query: str,
    account_slug: str | None = None,
    limit: int = DEFAULT_RESULT_LIMIT,
    lexical_limit: int = LEXICAL_DEFAULT_LIMIT,
    vector_limit: int = VECTOR_DEFAULT_LIMIT,
    rrf_k: int = DEFAULT_K,
) -> RetrievalResult | None:
    """Returns None when `account_slug` is given but not visible to this
    user (nonexistent, cross-org, or zero-permitted-document account) —
    callers must turn that into the same uniform 404 Milestone 2 already
    uses elsewhere, not a distinguishing error."""
    account_id: int | None = None
    if account_slug is not None:
        account = get_visible_account(db, user_ctx, account_slug)
        if account is None:
            return None
        account_id = account.id

    t0 = time.perf_counter()
    lexical_candidates = lexical_search(db, user_ctx, query, account_id=account_id, limit=lexical_limit)
    t1 = time.perf_counter()

    query_embedding = embedding_provider.embed_query(query)
    vector_candidates = vector_search(db, user_ctx, query_embedding, account_id=account_id, limit=vector_limit)
    t2 = time.perf_counter()

    merged = reciprocal_rank_fusion(lexical_candidates, vector_candidates, k=rrf_k, limit=limit)
    t3 = time.perf_counter()

    hits = _build_hits(db, merged)

    trace = RetrievalTrace(
        query=query,
        user_id=user_ctx.id,
        account_scope=account_slug if account_slug is not None else "all",
        lexical_candidates=[
            TraceCandidate(chunk_id=c.chunk_id, rank=c.rank, score=c.score) for c in lexical_candidates
        ],
        vector_candidates=[
            TraceCandidate(chunk_id=c.chunk_id, rank=c.rank, score=c.score) for c in vector_candidates
        ],
        merged=list(merged),
        returned_chunk_ids=[hit.chunk_id for hit in hits],
        timings_ms={
            "lexical_ms": (t1 - t0) * 1000,
            "vector_ms": (t2 - t1) * 1000,
            "merge_ms": (t3 - t2) * 1000,
            "total_ms": (t3 - t0) * 1000,
        },
    )
    return RetrievalResult(hits=hits, trace=trace)


def _build_hits(db: Session, merged) -> list[RetrievalHit]:
    """Fetches display metadata for the final merged chunk ids. No
    permission re-check here: every id in `merged` already came from a
    permission-scoped lexical/vector query, so this is a plain metadata
    lookup, not a second authorization decision."""
    chunk_ids = [entry.chunk_id for entry in merged]
    if not chunk_ids:
        return []

    rows = db.execute(
        select(
            Chunk.id,
            Chunk.document_id,
            Account.id.label("account_id"),
            SourceDocument.source,
            SourceDocument.title,
            SourceDocument.occurred_at,
            Chunk.content,
        )
        .join(SourceDocument, SourceDocument.id == Chunk.document_id)
        .join(Account, Account.id == SourceDocument.account_id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    metadata_by_id = {row.id: row for row in rows}

    hits = []
    for entry in merged:
        row = metadata_by_id.get(entry.chunk_id)
        if row is None:
            continue  # defensive: a chunk deleted between candidate generation and this fetch
        hits.append(
            RetrievalHit(
                chunk_id=row.id,
                document_id=row.document_id,
                account_id=row.account_id,
                source=row.source,
                title=row.title,
                content=row.content,
                occurred_at=row.occurred_at,
                lexical_rank=entry.lexical_rank,
                vector_rank=entry.vector_rank,
                hybrid_score=entry.hybrid_score,
            )
        )
    return hits
