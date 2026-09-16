from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_context
from app.generation.errors import GenerationFailure
from app.generation.provider import AnswerGenerator, GeminiAnswerGenerator
from app.generation.service import answer as generate_answer
from app.generation.types import AnswerResult
from app.permissions.resolver import UserContext
from app.retrieval.embeddings import EmbeddingProvider
from app.routers.search import get_embedding_provider
from app.schemas.answer import (
    AnswerRequest,
    AnswerResponse,
    CitationOut,
    GenerationTraceOut,
)
from app.schemas.search import (
    MergedTraceEntryOut,
    RetrievalTraceOut,
    TraceCandidateOut,
)

router = APIRouter()

# Lazy singleton, same pattern as search.py's embedding provider: the real
# Gemini client loads on first use, not at import time, and is exposed as
# a FastAPI dependency so tests can override it with FakeAnswerGenerator.
_answer_generator = GeminiAnswerGenerator()


def get_answer_generator() -> AnswerGenerator:
    return _answer_generator


def _to_response(result: AnswerResult) -> AnswerResponse:
    trace = result.trace
    retrieval_trace = trace.retrieval_trace
    return AnswerResponse(
        answer=result.answer,
        status=result.status,
        citations=[
            CitationOut(
                citation_id=c.citation_id,
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                source=c.source,
                title=c.title,
                occurred_at=c.occurred_at,
                excerpt=c.excerpt,
            )
            for c in result.citations
        ],
        trace=GenerationTraceOut(
            query=trace.query,
            user_id=trace.user_id,
            account_slug=trace.account_slug,
            retrieval_trace=RetrievalTraceOut(
                query=retrieval_trace.query,
                user_id=retrieval_trace.user_id,
                account_scope=retrieval_trace.account_scope,
                lexical_candidates=[
                    TraceCandidateOut(chunk_id=c.chunk_id, rank=c.rank, score=c.score)
                    for c in retrieval_trace.lexical_candidates
                ],
                vector_candidates=[
                    TraceCandidateOut(chunk_id=c.chunk_id, rank=c.rank, score=c.score)
                    for c in retrieval_trace.vector_candidates
                ],
                merged=[
                    MergedTraceEntryOut(
                        chunk_id=m.chunk_id, hybrid_score=m.hybrid_score, lexical_rank=m.lexical_rank,
                        vector_rank=m.vector_rank,
                    )
                    for m in retrieval_trace.merged
                ],
                returned_chunk_ids=retrieval_trace.returned_chunk_ids,
                timings_ms=retrieval_trace.timings_ms,
            ),
            context_citation_ids=trace.context_citation_ids,
            context_commitment_ids=trace.context_commitment_ids,
            generator_model=trace.generator_model,
            generation_status=trace.generation_status,
            claims_emitted=trace.claims_emitted,
            claims_dropped=trace.claims_dropped,
            invalid_ids_seen=trace.invalid_ids_seen,
            timings_ms=trace.timings_ms,
        ),
    )


@router.post("/answer", response_model=AnswerResponse)
def answer_question(
    request: AnswerRequest,
    user_ctx: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    generator: AnswerGenerator = Depends(get_answer_generator),
) -> AnswerResponse:
    try:
        result = generate_answer(db, user_ctx, embedding_provider, generator, request.query, request.account_slug)
    except GenerationFailure:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Answer generation failed"
        ) from None
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _to_response(result)
