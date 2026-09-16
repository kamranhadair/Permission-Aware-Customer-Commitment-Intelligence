"""Integration tests for app/generation/service.py:answer() against a real
test database, using FakeAnswerGenerator throughout — no network calls.
Mirrors the conventions in test_retrieval_service.py."""

from app.generation.errors import GenerationFailure
from app.generation.provider import FakeAnswerGenerator
from app.generation.service import INSUFFICIENT_EVIDENCE_MESSAGE, answer
from app.generation.types import Claim, GeneratedAnswer
from app.models import DocumentUserAcl, GroupMembership
from app.permissions.resolver import get_user_context
from app.retrieval.embeddings import FakeEmbeddingProvider
from tests.factories import (
    add_membership,
    grant_group_acl,
    grant_user_acl,
    link_evidence,
    make_account,
    make_chunk,
    make_commitment,
    make_document,
    make_group,
    make_org,
    make_user,
)

import pytest

PROVIDER = FakeEmbeddingProvider()


def _embed(db, chunk) -> None:
    chunk.embedding = PROVIDER.embed_documents([chunk.content])[0]
    db.flush()


# --- account scoping ---------------------------------------------------------


def test_inaccessible_account_returns_none(db):
    org = make_org(db)
    make_account(db, org, "acme")
    user = make_user(db, org, "u1@x.com")
    ctx = get_user_context(db, user.id)
    assert answer(db, ctx, PROVIDER, FakeAnswerGenerator(), "q", "acme") is None


def test_nonexistent_account_returns_none(db):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")
    ctx = get_user_context(db, user.id)
    assert answer(db, ctx, PROVIDER, FakeAnswerGenerator(), "q", "does-not-exist") is None


def test_cross_org_account_returns_none(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    make_account(db, org_b, "globex")
    user_a = make_user(db, org_a, "u1@a.com")
    ctx = get_user_context(db, user_a.id)
    assert answer(db, ctx, PROVIDER, FakeAnswerGenerator(), "q", "globex") is None


# --- zero-context short circuit ---------------------------------------------


def test_zero_context_short_circuits_without_calling_generator(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)  # permitted, but has zero chunks
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    ctx = get_user_context(db, user.id)

    generator = FakeAnswerGenerator()
    result = answer(db, ctx, PROVIDER, generator, "anything", "acme")

    assert result is not None
    assert result.status == "insufficient_evidence"
    assert result.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.citations == []
    assert generator.last_query is None  # never invoked


# --- direct-user / group evidence can support an answer ---------------------


def test_direct_user_permitted_evidence_supports_answer(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="SSO login fails for Acme admins")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    ctx = get_user_context(db, user.id)

    def responder(query, context):
        assert context.evidence
        e1 = context.evidence[0].citation_id
        return GeneratedAnswer(
            status="answered", claims=[Claim(text="SSO fails for admins.", citation_ids=[e1], claim_type="evidence")]
        )

    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "SSO login fails", "acme")
    assert result.status == "answered"
    assert result.citations[0].chunk_id == chunk.id
    assert "[E1]" in result.answer


def test_group_permitted_evidence_supports_answer(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="export rate limit roadmap detail")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)
    ctx = get_user_context(db, user.id)

    def responder(query, context):
        e1 = context.evidence[0].citation_id
        return GeneratedAnswer(status="answered", claims=[Claim(text="Roadmap detail.", citation_ids=[e1], claim_type="evidence")])

    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "export rate limit roadmap", "acme")
    assert result.status == "answered"
    assert result.citations[0].chunk_id == chunk.id


# --- security -----------------------------------------------------------------


def test_unauthorized_chunk_never_enters_generation_context(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    visible_doc = make_document(db, account)
    hidden_doc = make_document(db, account)
    visible_chunk = make_chunk(db, visible_doc, content="visible onboarding notes")
    hidden_chunk = make_chunk(db, hidden_doc, content="hidden confidential onboarding secret")
    _embed(db, visible_chunk)
    _embed(db, hidden_chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)
    ctx = get_user_context(db, user.id)

    captured = {}

    def responder(query, context):
        captured["context"] = context
        e1 = context.evidence[0].citation_id
        return GeneratedAnswer(status="answered", claims=[Claim(text="visible fact.", citation_ids=[e1], claim_type="evidence")])

    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "onboarding notes", "acme")

    context = captured["context"]
    assert {c.chunk_id for c in context.evidence} == {visible_chunk.id}
    assert all("hidden confidential" not in c.content for c in context.evidence)
    assert result.citations[0].chunk_id == visible_chunk.id


def test_unauthorized_chunk_cannot_appear_in_citations_even_if_generator_tries(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    visible_doc = make_document(db, account)
    visible_chunk = make_chunk(db, visible_doc, content="visible content")
    _embed(db, visible_chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)
    ctx = get_user_context(db, user.id)

    # A misbehaving/compromised generator tries to cite an id it was never
    # given ("E99" — structurally guaranteed not to exist since only one
    # chunk is in context) instead of the real E1.
    bad = GeneratedAnswer(status="answered", claims=[Claim(text="fabricated", citation_ids=["E99"], claim_type="evidence")])

    with pytest.raises(GenerationFailure):
        answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=bad), "visible content", "acme")


def test_group_membership_revocation_affects_next_answer(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="roadmap detail for product group only")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)

    anchor_doc = make_document(db, account)
    anchor_chunk = make_chunk(db, anchor_doc, content="an unrelated always-visible anchor document")
    _embed(db, anchor_chunk)
    grant_user_acl(db, anchor_doc, user)  # keeps the account (and some evidence) visible after revocation

    ctx = get_user_context(db, user.id)
    captured = {}

    def responder(query, context):
        captured["ids"] = {c.chunk_id for c in context.evidence}
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "roadmap detail", "acme")
    assert chunk.id in captured["ids"]

    db.query(GroupMembership).filter_by(user_id=user.id, group_id=group.id).delete()
    db.flush()

    ctx_after = get_user_context(db, user.id)
    answer(db, ctx_after, PROVIDER, FakeAnswerGenerator(respond_with=responder), "roadmap detail", "acme")
    assert chunk.id not in captured["ids"]


def test_document_acl_revocation_affects_next_answer(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="confidential contract terms")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    anchor_doc = make_document(db, account)
    anchor_chunk = make_chunk(db, anchor_doc, content="an unrelated always-visible anchor document")
    _embed(db, anchor_chunk)
    grant_user_acl(db, anchor_doc, user)

    ctx = get_user_context(db, user.id)
    captured = {}

    def responder(query, context):
        captured["ids"] = {c.chunk_id for c in context.evidence}
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "confidential contract terms", "acme")
    assert chunk.id in captured["ids"]

    db.query(DocumentUserAcl).filter_by(document_id=doc.id, user_id=user.id).delete()
    db.flush()

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "confidential contract terms", "acme")
    assert chunk.id not in captured["ids"]


def test_cross_org_evidence_cannot_influence_generation(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "shared-slug")
    account_b = make_account(db, org_b, "shared-slug")

    doc_a = make_document(db, account_a)
    chunk_a = make_chunk(db, doc_a, content="org a evidence")
    _embed(db, chunk_a)
    doc_b = make_document(db, account_b)
    chunk_b = make_chunk(db, doc_b, content="org b evidence")
    _embed(db, chunk_b)

    user_a = make_user(db, org_a, "u1@a.com")
    grant_user_acl(db, doc_a, user_a)
    ctx = get_user_context(db, user_a.id)

    captured = {}

    def responder(query, context):
        captured["ids"] = {c.chunk_id for c in context.evidence}
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "evidence", "shared-slug")
    assert captured["ids"] == {chunk_a.id}
    assert chunk_b.id not in captured["ids"]


# --- grounding / citation-failure semantics (constraint #3) ------------------


def test_answered_with_all_claims_invalid_raises_generation_failure_not_insufficient(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="some evidence")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    ctx = get_user_context(db, user.id)

    bad = GeneratedAnswer(status="answered", claims=[Claim(text="unsupported", citation_ids=[], claim_type="evidence")])
    with pytest.raises(GenerationFailure):
        answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=bad), "some evidence", "acme")


def test_answered_with_some_valid_some_invalid_claims_returns_only_valid(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="valid evidence content")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    ctx = get_user_context(db, user.id)

    def responder(query, context):
        e1 = context.evidence[0].citation_id
        return GeneratedAnswer(
            status="answered",
            claims=[
                Claim(text="Grounded fact.", citation_ids=[e1], claim_type="evidence"),
                Claim(text="Fabricated fact.", citation_ids=["E99"], claim_type="evidence"),
            ],
        )

    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "valid evidence", "acme")
    assert result.status == "answered"
    assert "Grounded fact." in result.answer
    assert "Fabricated fact." not in result.answer
    assert result.trace.claims_dropped == 1
    assert "E99" in result.trace.invalid_ids_seen


def test_explicit_provider_insufficient_evidence_returns_200_insufficient(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="some tangential evidence")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    ctx = get_user_context(db, user.id)

    declared = GeneratedAnswer(status="insufficient_evidence", claims=[])
    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=declared), "unrelated question", "acme")
    assert result.status == "insufficient_evidence"
    assert result.answer == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.citations == []


# --- commitment / authority semantics ----------------------------------------


def test_commitment_claim_cross_commitment_provenance_rejected_end_to_end(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk_1 = make_chunk(db, doc, content="sales said november")
    chunk_2 = make_chunk(db, doc, content="product target roadmap")
    _embed(db, chunk_1)
    _embed(db, chunk_2)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    commitment_1 = make_commitment(db, account, statement="Sales told Acme November", authority="sales_unapproved")
    link_evidence(db, commitment_1, chunk_1, "supporting")
    commitment_2 = make_commitment(db, account, statement="Product roadmap target", authority="product_target")
    link_evidence(db, commitment_2, chunk_2, "supporting")

    ctx = get_user_context(db, user.id)

    def responder(query, context):
        c1 = next(c for c in context.commitments if c.authority == "sales_unapproved")
        c2 = next(c for c in context.commitments if c.authority == "product_target")
        # Attempt to back C1's authority using C2's evidence — cross-commitment provenance.
        bad_citation = c2.supporting_citation_ids[0]
        return GeneratedAnswer(
            status="answered",
            claims=[Claim(text="approved via cross reference", citation_ids=[bad_citation], claim_type="commitment", commitment_context_id=c1.citation_id)],
        )

    with pytest.raises(GenerationFailure):
        answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "november commitment", "acme")


def test_authority_value_preserved_distinctly_end_to_end(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="contract terms for delivery")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    commitment = make_commitment(db, account, statement="Contractual delivery obligation", authority="contractual")
    link_evidence(db, commitment, chunk, "supporting")
    ctx = get_user_context(db, user.id)

    captured = {}

    def responder(query, context):
        captured["authorities"] = {c.authority for c in context.commitments}
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "contract terms", "acme")
    assert captured["authorities"] == {"contractual"}


def test_permitted_conflicting_evidence_surfaced(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    support_chunk = make_chunk(db, doc, content="AE told customer November")
    conflict_chunk = make_chunk(db, doc, content="Product said do not promise November")
    _embed(db, support_chunk)
    _embed(db, conflict_chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    commitment = make_commitment(db, account, statement="November SSO", authority="sales_unapproved")
    link_evidence(db, commitment, support_chunk, "supporting")
    link_evidence(db, commitment, conflict_chunk, "conflicting")
    ctx = get_user_context(db, user.id)

    def responder(query, context):
        c1 = context.commitments[0]
        return GeneratedAnswer(
            status="answered",
            claims=[
                Claim(
                    text="There is conflicting evidence about the date.",
                    citation_ids=[c1.supporting_citation_ids[0], c1.conflicting_citation_ids[0]],
                    claim_type="commitment",
                    commitment_context_id=c1.citation_id,
                )
            ],
        )

    result = answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "November SSO", "acme")
    assert result.status == "answered"
    cited_chunks = {c.chunk_id for c in result.citations}
    assert cited_chunks == {support_chunk.id, conflict_chunk.id}


def test_forbidden_conflicting_evidence_not_surfaced(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    support_chunk = make_chunk(db, doc, content="AE told customer November")
    forbidden_conflict_doc = make_document(db, account)
    forbidden_conflict_chunk = make_chunk(db, forbidden_conflict_doc, content="secret internal conflicting note")
    _embed(db, support_chunk)
    _embed(db, forbidden_conflict_chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)  # no grant on forbidden_conflict_doc

    commitment = make_commitment(db, account, statement="November SSO", authority="sales_unapproved")
    link_evidence(db, commitment, support_chunk, "supporting")
    link_evidence(db, commitment, forbidden_conflict_chunk, "conflicting")
    ctx = get_user_context(db, user.id)

    captured = {}

    def responder(query, context):
        c1 = context.commitments[0]
        captured["conflicting"] = c1.conflicting_citation_ids
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "November SSO", "acme")
    assert captured["conflicting"] == []  # forbidden chunk never made it into context at all


def test_commitment_with_no_permitted_supporting_evidence_is_hidden(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    forbidden_doc = make_document(db, account)
    forbidden_chunk = make_chunk(db, forbidden_doc, content="only evidence for this commitment")
    _embed(db, forbidden_chunk)

    anchor_doc = make_document(db, account)
    anchor_chunk = make_chunk(db, anchor_doc, content="unrelated anchor content")
    _embed(db, anchor_chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, anchor_doc, user)  # keeps account visible; no grant on forbidden_doc

    commitment = make_commitment(db, account, statement="Hidden commitment", authority="product_approved")
    link_evidence(db, commitment, forbidden_chunk, "supporting")
    ctx = get_user_context(db, user.id)

    captured = {}

    def responder(query, context):
        captured["commitment_ids"] = {c.commitment_id for c in context.commitments}
        return GeneratedAnswer(status="insufficient_evidence", claims=[])

    answer(db, ctx, PROVIDER, FakeAnswerGenerator(respond_with=responder), "hidden commitment", "acme")
    assert commitment.id not in captured["commitment_ids"]
