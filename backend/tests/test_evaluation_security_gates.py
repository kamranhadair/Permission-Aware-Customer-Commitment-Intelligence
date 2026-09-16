"""Proves the automated structural security gates actually detect an
unauthorized chunk/document id — the load-bearing regression for Milestone
6's hard zero-tolerance gates. Uses the real Postgres test database via
factories (matching every other backend test's convention), not the full
evaluation runner.
"""

from __future__ import annotations

from app.evaluation.security_gates import check_generation_gates, check_retrieval_gates, merge_reports
from app.retrieval.types import MergedTraceEntry, RetrievalTrace, TraceCandidate
from tests.factories import make_account, make_chunk, make_document, make_org


def _trace(lexical_chunk_ids, vector_chunk_ids, merged_chunk_ids) -> RetrievalTrace:
    return RetrievalTrace(
        query="q",
        user_id=1,
        account_scope="all",
        lexical_candidates=[TraceCandidate(chunk_id=cid, rank=i + 1, score=1.0) for i, cid in enumerate(lexical_chunk_ids)],
        vector_candidates=[TraceCandidate(chunk_id=cid, rank=i + 1, score=0.1) for i, cid in enumerate(vector_chunk_ids)],
        merged=[MergedTraceEntry(chunk_id=cid, hybrid_score=1.0, lexical_rank=1, vector_rank=1) for cid in merged_chunk_ids],
        returned_chunk_ids=list(merged_chunk_ids),
        timings_ms={},
    )


def test_retrieval_gates_flag_unauthorized_chunk_in_every_channel(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    permitted_doc = make_document(db, account)
    forbidden_doc = make_document(db, account)
    permitted_chunk = make_chunk(db, permitted_doc)
    forbidden_chunk = make_chunk(db, forbidden_doc)

    trace = _trace(
        lexical_chunk_ids=[permitted_chunk.id, forbidden_chunk.id],
        vector_chunk_ids=[forbidden_chunk.id],
        merged_chunk_ids=[permitted_chunk.id, forbidden_chunk.id],
    )

    report = check_retrieval_gates(db, {permitted_doc.id}, trace)

    assert report.count("unauthorized_lexical_candidates") == 1
    assert report.count("unauthorized_vector_candidates") == 1
    assert report.count("unauthorized_hybrid_candidates") == 1
    assert not report.all_clear
    assert all(v.document_id == forbidden_doc.id for v in report.violations)


def test_retrieval_gates_clean_when_everything_permitted(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc)

    trace = _trace([chunk.id], [chunk.id], [chunk.id])
    report = check_retrieval_gates(db, {doc.id}, trace)

    assert report.all_clear
    assert report.summary() == {
        "unauthorized_lexical_candidates": 0,
        "unauthorized_vector_candidates": 0,
        "unauthorized_hybrid_candidates": 0,
        "unauthorized_generation_context_chunks": 0,
        "unauthorized_citations": 0,
    }


def test_generation_gates_flag_unauthorized_context_and_citation():
    report = check_generation_gates(
        permitted_document_ids={1},
        context_document_ids=[1, 2],
        citation_document_ids=[1, 2],
    )
    assert report.count("unauthorized_generation_context_chunks") == 1
    assert report.count("unauthorized_citations") == 1
    assert not report.all_clear


def test_generation_gates_clean_when_everything_permitted():
    report = check_generation_gates(permitted_document_ids={1, 2}, context_document_ids=[1, 2], citation_document_ids=[1])
    assert report.all_clear


def test_merge_reports_combines_violations():
    a = check_generation_gates(permitted_document_ids=set(), context_document_ids=[1], citation_document_ids=[])
    b = check_generation_gates(permitted_document_ids=set(), context_document_ids=[], citation_document_ids=[2])
    merged = merge_reports(a, b)
    assert len(merged.violations) == 2
    assert not merged.all_clear
