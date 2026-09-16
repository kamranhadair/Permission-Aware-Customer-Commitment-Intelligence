"""Domain types for generation. Plain frozen dataclasses, matching the
convention in app/retrieval/types.py — no ACL fields, no hidden-candidate
counts, nothing that isn't safe to eventually surface.

`C*` (CommitmentContext.citation_id) and `E*` (ContextChunk.citation_id) are
deliberately different id spaces: `E*` is the only thing a Claim may cite in
`citation_ids`, and a `C*` id is never a valid citation target (see
app/generation/validation.py). `C*` exists purely so a "commitment" claim can
say *which* structured commitment it is describing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.retrieval.types import RetrievalTrace


@dataclass(frozen=True)
class ContextChunk:
    citation_id: str  # "E1".."En"
    chunk_id: int
    document_id: int
    source: str
    title: str
    occurred_at: datetime
    content: str


@dataclass(frozen=True)
class CommitmentContext:
    citation_id: str  # "C1".."Cn" — internal context label, never a valid claim citation
    commitment_id: int
    statement: str
    authority: str
    status: str
    # Both lists are always subsets of the citation_ids present in the
    # GenerationContext.evidence this block was built alongside — never a
    # dangling reference to an id that got truncated out of context.
    supporting_citation_ids: list[str]
    conflicting_citation_ids: list[str]


@dataclass(frozen=True)
class GenerationContext:
    evidence: list[ContextChunk]
    commitments: list[CommitmentContext]


ClaimType = Literal["evidence", "commitment"]
AnswerStatus = Literal["answered", "insufficient_evidence"]


@dataclass(frozen=True)
class Claim:
    text: str
    citation_ids: list[str] = field(default_factory=list)
    claim_type: ClaimType = "evidence"
    # Required (and validated) when claim_type == "commitment"; must stay
    # None for claim_type == "evidence" — see validate_and_filter_claims.
    commitment_context_id: str | None = None


@dataclass(frozen=True)
class GeneratedAnswer:
    """The provider's own claimed status plus whatever claims it produced —
    not yet grounding-validated. See validation.py for what happens next."""

    status: AnswerStatus
    claims: list[Claim]


@dataclass(frozen=True)
class Citation:
    citation_id: str
    chunk_id: int
    document_id: int
    source: str
    title: str
    occurred_at: datetime
    excerpt: str


@dataclass(frozen=True)
class GenerationTrace:
    query: str
    user_id: int
    account_slug: str
    retrieval_trace: RetrievalTrace
    context_citation_ids: list[str]
    context_commitment_ids: list[str]
    generator_model: str
    generation_status: str
    claims_emitted: int
    claims_dropped: int
    invalid_ids_seen: list[str]
    timings_ms: dict[str, float]


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    status: AnswerStatus
    citations: list[Citation]
    trace: GenerationTrace
