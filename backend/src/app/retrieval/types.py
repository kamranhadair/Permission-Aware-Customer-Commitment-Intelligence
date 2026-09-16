"""Result and trace contracts for retrieval. No ACL data, no
"filtered out" counts — see module docstrings in service.py for why the
trace is safe by construction rather than by redaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LexicalCandidate:
    chunk_id: int
    document_id: int
    rank: int  # 1-indexed position within the lexical channel
    score: float


@dataclass(frozen=True)
class VectorCandidate:
    chunk_id: int
    document_id: int
    rank: int  # 1-indexed position within the vector channel
    score: float  # cosine distance — lower is closer


@dataclass(frozen=True)
class RetrievalHit:
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


@dataclass(frozen=True)
class TraceCandidate:
    chunk_id: int
    rank: int | None
    score: float


@dataclass(frozen=True)
class MergedTraceEntry:
    chunk_id: int
    hybrid_score: float
    lexical_rank: int | None
    vector_rank: int | None


@dataclass(frozen=True)
class RetrievalTrace:
    query: str
    user_id: int
    account_scope: str  # "all" or the requested account_slug
    lexical_candidates: list[TraceCandidate]
    vector_candidates: list[TraceCandidate]
    merged: list[MergedTraceEntry]
    returned_chunk_ids: list[int]
    timings_ms: dict[str, float]


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[RetrievalHit]
    trace: RetrievalTrace
