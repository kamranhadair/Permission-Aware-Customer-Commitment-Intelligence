from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_context
from app.permissions.resolver import UserContext
from app.retrieval.embeddings import BgeEmbeddingProvider, EmbeddingProvider
from app.retrieval.service import retrieve
from app.retrieval.types import RetrievalResult
from app.schemas.search import (
    MergedTraceEntryOut,
    RetrievalHitOut,
    RetrievalTraceOut,
    SearchRequest,
    SearchResponse,
    TraceCandidateOut,
)

router = APIRouter()

# Lazy singleton: the real model loads on first embed call, not at import
# time. Exposed as a FastAPI dependency (not a bare module call in the
# route) so tests can override it with FakeEmbeddingProvider exactly like
# get_db is overridden — the security test suite never has to load torch.
_embedding_provider = BgeEmbeddingProvider()


def get_embedding_provider() -> EmbeddingProvider:
    return _embedding_provider


def _to_response(result: RetrievalResult) -> SearchResponse:
    return SearchResponse(
        results=[
            RetrievalHitOut(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                account_id=hit.account_id,
                source=hit.source,
                title=hit.title,
                content=hit.content,
                occurred_at=hit.occurred_at,
                lexical_rank=hit.lexical_rank,
                vector_rank=hit.vector_rank,
                hybrid_score=hit.hybrid_score,
            )
            for hit in result.hits
        ],
        trace=RetrievalTraceOut(
            query=result.trace.query,
            user_id=result.trace.user_id,
            account_scope=result.trace.account_scope,
            lexical_candidates=[
                TraceCandidateOut(chunk_id=c.chunk_id, rank=c.rank, score=c.score)
                for c in result.trace.lexical_candidates
            ],
            vector_candidates=[
                TraceCandidateOut(chunk_id=c.chunk_id, rank=c.rank, score=c.score)
                for c in result.trace.vector_candidates
            ],
            merged=[
                MergedTraceEntryOut(
                    chunk_id=m.chunk_id,
                    hybrid_score=m.hybrid_score,
                    lexical_rank=m.lexical_rank,
                    vector_rank=m.vector_rank,
                )
                for m in result.trace.merged
            ],
            returned_chunk_ids=result.trace.returned_chunk_ids,
            timings_ms=result.trace.timings_ms,
        ),
    )


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> SearchResponse:
    result = retrieve(db, user_ctx, embedding_provider, request.query, account_slug=request.account_slug)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _to_response(result)
