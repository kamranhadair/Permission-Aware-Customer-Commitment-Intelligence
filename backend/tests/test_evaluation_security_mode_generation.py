"""Proves `--mode security` actually exercises the real Milestone 5
generation path (context construction, citation/provenance validation),
not just retrieval — the gap identified in follow-up review. Uses the real
seeded evaluation fixtures (not synthetic factories) since the whole point
is proving this against the actual golden-dataset personas/ACLs/commitments.
"""

from __future__ import annotations

from app.evaluation import personas as personas_module
from app.evaluation.fixtures_loader import embed_all_chunks, ingest_all_fixtures, seed_commitments
from app.evaluation.runner import (
    _load_dataset,
    _resolve_doc_ids_to_refs,
    _run_generation_case_with_visibility,
    _score_security_generation_case,
    security_mode_fake_answer,
)
from app.evaluation.stable_ids import DocumentIdentity, document_ids_for
from app.generation.provider import FakeAnswerGenerator
from app.permissions.resolver import get_user_context
from app.retrieval.embeddings import FakeEmbeddingProvider


def _seed(db) -> personas_module.EvalSeed:
    seed = personas_module.seed(db)
    ingest_all_fixtures(db, seed.org.id)
    seed_commitments(db, seed.accounts)
    embed_all_chunks(db, FakeEmbeddingProvider())
    return seed


def _case(case_id: str):
    return next(c for c in _load_dataset().cases if c.id == case_id)


def _fake_generator() -> FakeAnswerGenerator:
    return FakeAnswerGenerator(respond_with=security_mode_fake_answer)


def test_security_mode_generation_case_actually_invokes_context_construction(db):
    seed = _seed(db)
    case = _case("dl-01")  # alice, acme-corp — real permitted evidence exists
    user_ctx = get_user_context(db, seed.users[case.persona].id)

    result = _score_security_generation_case(
        db, seed, user_ctx, FakeEmbeddingProvider(), _fake_generator(), case, mode="security"
    )

    assert result.generation is not None, "build_context must have run and produced a payload"
    assert result.generation["context_citation_ids"], "real permitted evidence should have produced E* ids"
    assert result.status_actual == "answered"
    assert result.security_violation_count == 0


def test_forbidden_candidate_absent_at_every_stage(db):
    seed = _seed(db)
    case = _case("pr-02")  # alice, acme-corp, forbidden = C-ACME-INTERNAL (product/exec only)
    assert case.forbidden_evidence, "pr-02 must declare a forbidden reference for this test to mean anything"

    user_ctx = get_user_context(db, seed.users[case.persona].id)
    forbidden_doc_ids = set()
    for ref in case.forbidden_evidence:
        forbidden_doc_ids |= document_ids_for(
            db, seed.org.id, case.account_slug, [DocumentIdentity(source=ref.source, external_id=ref.external_id)]
        )
    assert forbidden_doc_ids, "forbidden_evidence must resolve to a real document"

    raw_claims, context, valid_claims, retrieval_result, status_actual = _run_generation_case_with_visibility(
        db, user_ctx, FakeEmbeddingProvider(), _fake_generator(), case.query, case.account_slug
    )

    # Stage 1: retrieval candidates (lexical/vector/hybrid).
    from app.evaluation.stable_ids import chunk_document_map

    candidate_chunk_ids = {c.chunk_id for c in retrieval_result.trace.lexical_candidates}
    candidate_chunk_ids |= {c.chunk_id for c in retrieval_result.trace.vector_candidates}
    candidate_chunk_ids |= {m.chunk_id for m in retrieval_result.trace.merged}
    candidate_doc_ids = set(chunk_document_map(db, candidate_chunk_ids).values())
    assert not (candidate_doc_ids & forbidden_doc_ids), "forbidden document appeared as a retrieval candidate"

    # Stage 2: generation context.
    context_doc_ids = {c.document_id for c in context.evidence}
    assert not (context_doc_ids & forbidden_doc_ids), "forbidden document entered GenerationContext.evidence"

    # Stage 3: surviving citations.
    cited_doc_ids = set()
    by_citation = {c.citation_id: c for c in context.evidence}
    for claim in valid_claims or []:
        for cid in claim.citation_ids:
            chunk = by_citation.get(cid)
            if chunk is not None:
                cited_doc_ids.add(chunk.document_id)
    assert not (cited_doc_ids & forbidden_doc_ids), "forbidden document survived as a citation"


def test_commitment_context_provenance_matches_persona_visibility(db):
    """acme-corp's sales_unapproved commitment has supporting=CALL-2001
    (account-management) and conflicting=C-ACME-INTERNAL (product/exec).
    dana sees both; alice sees only the supporting side. The built
    CommitmentContext's provenance lists must reflect exactly that — never
    more."""
    seed = _seed(db)

    call_2001_ids = document_ids_for(
        db, seed.org.id, "acme-corp", [DocumentIdentity(source="call", external_id="CALL-2001")]
    )
    internal_slack_ids = document_ids_for(
        db, seed.org.id, "acme-corp",
        [DocumentIdentity(source="slack", external_id="C-ACME-INTERNAL:1722000000.0001")],
    )
    assert call_2001_ids and internal_slack_ids

    query = "Are there any conflicting statements about the November SSO date?"

    dana_ctx = get_user_context(db, seed.users["dana"].id)
    _rc, dana_context, _vc, _rr, _st = _run_generation_case_with_visibility(
        db, dana_ctx, FakeEmbeddingProvider(), _fake_generator(), query, "acme-corp"
    )
    dana_commitments = [c for c in dana_context.commitments if c.authority == "sales_unapproved"]
    assert dana_commitments, "dana must see the sales_unapproved commitment"
    c1 = dana_commitments[0]
    supporting_docs = {
        chunk.document_id for chunk in dana_context.evidence if chunk.citation_id in c1.supporting_citation_ids
    }
    conflicting_docs = {
        chunk.document_id for chunk in dana_context.evidence if chunk.citation_id in c1.conflicting_citation_ids
    }
    assert supporting_docs == call_2001_ids
    assert conflicting_docs == internal_slack_ids, "dana sees both sides — conflicting must be populated"

    alice_ctx = get_user_context(db, seed.users["alice"].id)
    _rc2, alice_context, _vc2, _rr2, _st2 = _run_generation_case_with_visibility(
        db, alice_ctx, FakeEmbeddingProvider(), _fake_generator(), query, "acme-corp"
    )
    alice_commitments = [c for c in alice_context.commitments if c.authority == "sales_unapproved"]
    assert alice_commitments, "alice must still see the commitment (her supporting evidence is permitted)"
    c1_alice = alice_commitments[0]
    alice_conflicting_docs = {
        chunk.document_id for chunk in alice_context.evidence if chunk.citation_id in c1_alice.conflicting_citation_ids
    }
    assert alice_conflicting_docs == set(), (
        "the hidden conflicting evidence (C-ACME-INTERNAL) must never reach alice's CommitmentContext provenance, "
        "even though the same real commitment has conflicting evidence in the database"
    )
    assert not (internal_slack_ids & {chunk.document_id for chunk in alice_context.evidence}), (
        "C-ACME-INTERNAL must not even appear in alice's evidence list at all"
    )
