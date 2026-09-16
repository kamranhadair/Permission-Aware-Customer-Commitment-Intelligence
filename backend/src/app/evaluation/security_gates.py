"""The automated, structural, zero-tolerance security gates (Milestone 6
design section 3 / section 10). Every one of these is mechanically provable
from ids alone — no semantic judgment required — which is exactly why they
can be automatic. `unauthorized_facts_emitted` and `hidden_conflict_leakage`
are deliberately NOT here: whether a sentence semantically implies forbidden
content cannot be proven from citation ids alone, and a brittle keyword
search (checking for "however"/"conflict"/...) is not a security proof — see
the manual-review gates in report.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.evaluation.stable_ids import chunk_document_map
from app.retrieval.types import RetrievalTrace


@dataclass
class GateViolation:
    gate: str
    chunk_id: int
    document_id: int


@dataclass
class SecurityGateReport:
    violations: list[GateViolation] = field(default_factory=list)

    def count(self, gate: str) -> int:
        return sum(1 for v in self.violations if v.gate == gate)

    @property
    def all_clear(self) -> bool:
        return not self.violations

    def summary(self) -> dict[str, int]:
        gates = (
            "unauthorized_lexical_candidates",
            "unauthorized_vector_candidates",
            "unauthorized_hybrid_candidates",
            "unauthorized_generation_context_chunks",
            "unauthorized_citations",
        )
        return {gate: self.count(gate) for gate in gates}


def check_retrieval_gates(
    db: Session, permitted_document_ids: set[int], trace: RetrievalTrace
) -> SecurityGateReport:
    report = SecurityGateReport()
    all_chunk_ids = {c.chunk_id for c in trace.lexical_candidates}
    all_chunk_ids |= {c.chunk_id for c in trace.vector_candidates}
    all_chunk_ids |= {m.chunk_id for m in trace.merged}
    doc_by_chunk = chunk_document_map(db, all_chunk_ids)

    def _scan(gate: str, chunk_ids: set[int]) -> None:
        for chunk_id in chunk_ids:
            document_id = doc_by_chunk.get(chunk_id)
            if document_id is not None and document_id not in permitted_document_ids:
                report.violations.append(GateViolation(gate=gate, chunk_id=chunk_id, document_id=document_id))

    _scan("unauthorized_lexical_candidates", {c.chunk_id for c in trace.lexical_candidates})
    _scan("unauthorized_vector_candidates", {c.chunk_id for c in trace.vector_candidates})
    _scan("unauthorized_hybrid_candidates", {m.chunk_id for m in trace.merged})
    return report


def check_generation_gates(
    permitted_document_ids: set[int],
    context_document_ids: list[int],
    citation_document_ids: list[int],
) -> SecurityGateReport:
    """Unlike the retrieval gates, generation context/citations already carry
    document_id directly (ContextChunk/Citation), so no chunk_id lookup is
    needed here."""
    report = SecurityGateReport()
    for document_id in context_document_ids:
        if document_id not in permitted_document_ids:
            report.violations.append(
                GateViolation(gate="unauthorized_generation_context_chunks", chunk_id=-1, document_id=document_id)
            )
    for document_id in citation_document_ids:
        if document_id not in permitted_document_ids:
            report.violations.append(
                GateViolation(gate="unauthorized_citations", chunk_id=-1, document_id=document_id)
            )
    return report


def merge_reports(*reports: SecurityGateReport) -> SecurityGateReport:
    merged = SecurityGateReport()
    for r in reports:
        merged.violations.extend(r.violations)
    return merged
