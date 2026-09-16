from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.search import RetrievalTraceOut


class AnswerRequest(BaseModel):
    query: str
    # Required, unlike /search's optional account_slug: every product
    # question in scope for Milestone 5 ("What did we promise Acme?") is
    # inherently account-scoped, and cross-account commitment aggregation
    # is a materially harder, out-of-scope problem.
    account_slug: str


class CitationOut(BaseModel):
    citation_id: str
    chunk_id: int
    document_id: int
    source: str
    title: str
    occurred_at: datetime
    excerpt: str


class GenerationTraceOut(BaseModel):
    query: str
    user_id: int
    account_slug: str
    retrieval_trace: RetrievalTraceOut
    context_citation_ids: list[str]
    context_commitment_ids: list[str]
    generator_model: str
    generation_status: str
    claims_emitted: int
    claims_dropped: int
    invalid_ids_seen: list[str]
    timings_ms: dict[str, float]


class AnswerResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    citations: list[CitationOut]
    trace: GenerationTraceOut
