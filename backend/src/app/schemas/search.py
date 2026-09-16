from datetime import datetime

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    account_slug: str | None = None


class RetrievalHitOut(BaseModel):
    chunk_id: int
    document_id: int
    account_id: int
    source: str
    title: str
    content: str
    occurred_at: datetime
    lexical_rank: int | None
    vector_rank: int | None
    hybrid_score: float


class TraceCandidateOut(BaseModel):
    chunk_id: int
    rank: int | None
    score: float


class MergedTraceEntryOut(BaseModel):
    chunk_id: int
    hybrid_score: float
    lexical_rank: int | None
    vector_rank: int | None


class RetrievalTraceOut(BaseModel):
    query: str
    user_id: int
    account_scope: str
    lexical_candidates: list[TraceCandidateOut]
    vector_candidates: list[TraceCandidateOut]
    merged: list[MergedTraceEntryOut]
    returned_chunk_ids: list[int]
    timings_ms: dict[str, float]


class SearchResponse(BaseModel):
    results: list[RetrievalHitOut]
    trace: RetrievalTraceOut
