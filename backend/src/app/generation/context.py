"""Bounded, safe-by-construction context assembly.

Both inputs (`retrieval_hits`, `commitments`) are already permission-scoped
by the time they reach this module — this file does zero ACL logic itself,
it only formats and bounds already-safe data. Citation ids (`E*`/`C*`) are
assigned here, strictly after that permission filtering has happened.
"""

from __future__ import annotations

from app.permissions.resolver import ChunkView, CommitmentWithEvidence
from app.retrieval.types import RetrievalHit
from app.generation.types import CommitmentContext, ContextChunk, GenerationContext

# Retrieval already ranks by hybrid relevance (Milestone 4); this only bounds
# how many of those ranked hits are formatted into the prompt.
RETRIEVAL_CONTEXT_LIMIT = 8
# Hard cap on total evidence blocks sent to the model, including any
# commitment-only evidence appended beyond the retrieval hits. Retrieval
# hits are never truncated to make room for commitment extras — only the
# appended extras are ever dropped once this cap is hit.
MAX_EVIDENCE_CONTEXT = 10
# Hard cap on structured commitment blocks, independent of evidence count.
MAX_COMMITMENT_CONTEXT_BLOCKS = 10


def build_context(
    retrieval_hits: list[RetrievalHit],
    commitments: list[CommitmentWithEvidence],
) -> GenerationContext:
    evidence: list[ContextChunk] = []
    seen_chunk_ids: set[int] = set()

    for hit in retrieval_hits[:RETRIEVAL_CONTEXT_LIMIT]:
        evidence.append(
            ContextChunk(
                citation_id=f"E{len(evidence) + 1}",
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                source=hit.source,
                title=hit.title,
                occurred_at=hit.occurred_at,
                content=hit.content,
            )
        )
        seen_chunk_ids.add(hit.chunk_id)

    extra_chunks: dict[int, ChunkView] = {}
    for commitment in commitments:
        for chunk in (*commitment.supporting, *commitment.conflicting):
            if chunk.id not in seen_chunk_ids:
                extra_chunks.setdefault(chunk.id, chunk)

    ordered_extras = sorted(extra_chunks.values(), key=lambda c: (-c.occurred_at.timestamp(), c.id))
    remaining_slots = max(MAX_EVIDENCE_CONTEXT - len(evidence), 0)
    for chunk in ordered_extras[:remaining_slots]:
        evidence.append(
            ContextChunk(
                citation_id=f"E{len(evidence) + 1}",
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                source=chunk.source,
                title=chunk.title,
                occurred_at=chunk.occurred_at,
                content=chunk.content,
            )
        )
        seen_chunk_ids.add(chunk.id)

    chunk_id_to_citation = {chunk.chunk_id: chunk.citation_id for chunk in evidence}

    ordered_commitments = sorted(commitments, key=lambda c: (-c.promise_date.toordinal(), c.id))
    commitment_contexts: list[CommitmentContext] = []
    for commitment in ordered_commitments:
        if len(commitment_contexts) >= MAX_COMMITMENT_CONTEXT_BLOCKS:
            break
        supporting_ids = [
            chunk_id_to_citation[chunk.id] for chunk in commitment.supporting if chunk.id in chunk_id_to_citation
        ]
        # A commitment block is only included if at least one of its
        # supporting evidence chunks survived the MAX_EVIDENCE_CONTEXT
        # bound — never hand the model an authoritative authority/status
        # claim with nothing it could legally cite for it.
        if not supporting_ids:
            continue
        conflicting_ids = [
            chunk_id_to_citation[chunk.id] for chunk in commitment.conflicting if chunk.id in chunk_id_to_citation
        ]
        commitment_contexts.append(
            CommitmentContext(
                citation_id=f"C{len(commitment_contexts) + 1}",
                commitment_id=commitment.id,
                statement=commitment.statement,
                authority=commitment.authority,
                status=commitment.status,
                supporting_citation_ids=supporting_ids,
                conflicting_citation_ids=conflicting_ids,
            )
        )

    return GenerationContext(evidence=evidence, commitments=commitment_contexts)
