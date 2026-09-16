"""The one generation boundary. `answer()` is the only thing routers should
call — it resolves account scope, calls retrieval + the permission resolver
for commitments, builds bounded context, calls the generator, and applies
grounding validation. Mirrors app/retrieval/service.py:retrieve()'s shape.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.generation.context import RETRIEVAL_CONTEXT_LIMIT, build_context
from app.generation.errors import GenerationFailure
from app.generation.provider import AnswerGenerator
from app.generation.types import AnswerResult, Citation, GenerationContext, GenerationTrace
from app.generation.validation import render_answer, validate_and_filter_claims
from app.permissions.resolver import UserContext, get_visible_account, get_visible_commitments
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.service import retrieve
from app.retrieval.types import RetrievalTrace

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "No permitted evidence available to this user supports a grounded answer to this question."
)


def answer(
    db: Session,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    generator: AnswerGenerator,
    query: str,
    account_slug: str,
) -> AnswerResult | None:
    """Returns None when `account_slug` is not visible to this user
    (nonexistent, cross-org, or zero-permitted-document) — callers must
    turn that into the same uniform 404 every other account-scoped endpoint
    uses. Raises GenerationFailure (never returns it as a 200 status) for a
    provider/network error, a schema-invalid provider payload, or a
    schema-valid "answered" result where zero claims survive grounding
    validation — none of those prove the evidence was insufficient, they
    prove generation failed."""
    account = get_visible_account(db, user_ctx, account_slug)
    if account is None:
        return None

    t0 = time.perf_counter()
    retrieval_result = retrieve(
        db, user_ctx, embedding_provider, query, account_slug=account_slug, limit=RETRIEVAL_CONTEXT_LIMIT
    )
    assert retrieval_result is not None  # account_slug already resolved above
    commitments = get_visible_commitments(db, user_ctx, account.id)
    context = build_context(retrieval_result.hits, commitments)
    t1 = time.perf_counter()

    if not context.evidence and not context.commitments:
        return _insufficient_evidence_result(
            query, user_ctx, account_slug, retrieval_result.trace, context, generator,
            timings_ms={"context_ms": (t1 - t0) * 1000, "generation_ms": 0.0},
        )

    generated = generator.generate(query, context)  # may raise GenerationFailure
    t2 = time.perf_counter()
    timings_ms = {"context_ms": (t1 - t0) * 1000, "generation_ms": (t2 - t1) * 1000}

    if generated.status == "insufficient_evidence":
        return _insufficient_evidence_result(
            query, user_ctx, account_slug, retrieval_result.trace, context, generator, timings_ms
        )

    valid_claims, summary = validate_and_filter_claims(generated.claims, context)
    if not valid_claims:
        # The provider claimed "answered" but produced nothing grounded —
        # this is a generation failure, not a legitimate abstention.
        raise GenerationFailure("no claim survived citation/provenance validation")

    citations = _citations_for(valid_claims, context)
    return AnswerResult(
        answer=render_answer(valid_claims),
        status="answered",
        citations=citations,
        trace=_trace(
            query, user_ctx, account_slug, retrieval_result.trace, context, generator,
            generation_status="answered",
            claims_emitted=len(valid_claims),
            claims_dropped=summary.claims_dropped,
            invalid_ids_seen=summary.invalid_ids_seen,
            timings_ms=timings_ms,
        ),
    )


def _insufficient_evidence_result(
    query: str,
    user_ctx: UserContext,
    account_slug: str,
    retrieval_trace: RetrievalTrace,
    context: GenerationContext,
    generator: AnswerGenerator,
    timings_ms: dict[str, float],
) -> AnswerResult:
    return AnswerResult(
        answer=INSUFFICIENT_EVIDENCE_MESSAGE,
        status="insufficient_evidence",
        citations=[],
        trace=_trace(
            query, user_ctx, account_slug, retrieval_trace, context, generator,
            generation_status="insufficient_evidence",
            claims_emitted=0,
            claims_dropped=0,
            invalid_ids_seen=[],
            timings_ms=timings_ms,
        ),
    )


def _citations_for(claims, context: GenerationContext) -> list[Citation]:
    by_id = {chunk.citation_id: chunk for chunk in context.evidence}
    ordered_ids: list[str] = []
    for claim in claims:
        for cid in claim.citation_ids:
            if cid not in ordered_ids:
                ordered_ids.append(cid)
    return [
        Citation(
            citation_id=cid,
            chunk_id=by_id[cid].chunk_id,
            document_id=by_id[cid].document_id,
            source=by_id[cid].source,
            title=by_id[cid].title,
            occurred_at=by_id[cid].occurred_at,
            excerpt=by_id[cid].content,
        )
        for cid in ordered_ids
    ]


def _trace(
    query: str,
    user_ctx: UserContext,
    account_slug: str,
    retrieval_trace: RetrievalTrace,
    context: GenerationContext,
    generator: AnswerGenerator,
    generation_status: str,
    claims_emitted: int,
    claims_dropped: int,
    invalid_ids_seen: list[str],
    timings_ms: dict[str, float],
) -> GenerationTrace:
    return GenerationTrace(
        query=query,
        user_id=user_ctx.id,
        account_slug=account_slug,
        retrieval_trace=retrieval_trace,
        context_citation_ids=[chunk.citation_id for chunk in context.evidence],
        context_commitment_ids=[commitment.citation_id for commitment in context.commitments],
        generator_model=generator.model_name,
        generation_status=generation_status,
        claims_emitted=claims_emitted,
        claims_dropped=claims_dropped,
        invalid_ids_seen=invalid_ids_seen,
        timings_ms=timings_ms,
    )
