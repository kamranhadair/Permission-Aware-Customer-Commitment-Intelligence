from datetime import datetime, timezone

from sqlalchemy import select

from app.ingestion.service import ingest_document
from app.ingestion.types import NormalizedAcl, NormalizedDocument
from app.models import Chunk, CommitmentEvidence, DocumentGroupAcl, DocumentUserAcl, SourceDocument
from app.permissions.resolver import get_permitted_chunks, get_user_context
from tests.factories import add_membership, link_evidence, make_account, make_commitment, make_group, make_org, make_user


def _doc(
    external_id="EXT-1",
    content="Content",
    title="Title",
    sensitivity="internal",
    acl=NormalizedAcl(users=[], groups=[]),
    occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
):
    return NormalizedDocument(
        external_id=external_id, source="support", account_slug="acme-corp", title=title, content=content,
        occurred_at=occurred_at, sensitivity=sensitivity, acl=acl,
    )


def _setup(db):
    org = make_org(db, "Org")
    account = make_account(db, org, "acme-corp")
    alice = make_user(db, org, "alice@x.example")
    bob = make_user(db, org, "bob@x.example")
    product = make_group(db, org, "product")
    add_membership(db, bob, product)
    return org, account, alice, bob, product


def test_ingestion_is_idempotent(db):
    org, account, alice, bob, product = _setup(db)
    doc = _doc()

    first = ingest_document(db, org.id, doc)
    second = ingest_document(db, org.id, doc)

    assert first.outcome == "created"
    assert second.outcome == "unchanged"
    assert first.document_id == second.document_id
    assert len(db.scalars(select(SourceDocument)).all()) == 1


def test_repeated_ingestion_does_not_duplicate_chunks(db):
    org, account, alice, bob, product = _setup(db)
    doc = _doc(content=("a" * 600) + "\n\n" + ("b" * 600))  # forces 2 chunks under the 1000-char budget

    first = ingest_document(db, org.id, doc)
    chunk_ids_after_first = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}

    ingest_document(db, org.id, doc)
    chunk_ids_after_second = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}

    assert chunk_ids_after_first == chunk_ids_after_second
    assert len(chunk_ids_after_first) == 2


def test_content_change_replaces_stale_chunks(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(content="version one")
    first = ingest_document(db, org.id, doc_v1)
    old_chunk_ids = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}

    doc_v2 = _doc(content="version two, totally different")
    second = ingest_document(db, org.id, doc_v2)

    assert second.outcome == "updated"
    new_chunk_ids = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}
    assert old_chunk_ids.isdisjoint(new_chunk_ids)
    contents = [c.content for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))]
    assert contents == ["version two, totally different"]


def test_metadata_change_with_unchanged_content_updates_metadata_not_chunks(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(sensitivity="internal")
    first = ingest_document(db, org.id, doc_v1)
    chunk_ids_before = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}

    doc_v2 = _doc(sensitivity="confidential", title="New Title")
    second = ingest_document(db, org.id, doc_v2)

    assert second.outcome == "updated"
    row = db.get(SourceDocument, first.document_id)
    assert row.sensitivity == "confidential"
    assert row.title == "New Title"
    chunk_ids_after = {c.id for c in db.scalars(select(Chunk).where(Chunk.document_id == first.document_id))}
    assert chunk_ids_before == chunk_ids_after


def test_acl_removal_on_reingestion_revokes_access(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(acl=NormalizedAcl(users=[], groups=["product"]))
    first = ingest_document(db, org.id, doc_v1)

    bob_ctx = get_user_context(db, bob.id)
    assert len(get_permitted_chunks(db, bob_ctx, account.id)) == 1

    doc_v2 = _doc(acl=NormalizedAcl(users=[], groups=[]))
    second = ingest_document(db, org.id, doc_v2)

    assert second.outcome == "updated"
    bob_ctx = get_user_context(db, bob.id)
    assert get_permitted_chunks(db, bob_ctx, account.id) == []


def test_acl_addition_on_reingestion_grants_access(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(acl=NormalizedAcl(users=[], groups=[]))
    ingest_document(db, org.id, doc_v1)

    bob_ctx = get_user_context(db, bob.id)
    assert get_permitted_chunks(db, bob_ctx, account.id) == []

    doc_v2 = _doc(acl=NormalizedAcl(users=[], groups=["product"]))
    ingest_document(db, org.id, doc_v2)

    bob_ctx = get_user_context(db, bob.id)
    assert len(get_permitted_chunks(db, bob_ctx, account.id)) == 1


def _make_referenced_document(db, org, account):
    """Simulates a Milestone-2-style hand-seeded document with a chunk
    already tied to commitment_evidence, as if a future milestone had
    extracted a commitment from it. Ingestion must never see this as a
    fresh document (it's legacy — no external_id) directly; instead we
    ingest a document, then hand-link one of ITS chunks to a commitment,
    to simulate "this ingested content is now cited as evidence."
    """
    doc = _doc(content="original content", acl=NormalizedAcl(users=[], groups=["product"]))
    result = ingest_document(db, org.id, doc)
    row = db.get(SourceDocument, result.document_id)
    chunk = db.scalar(select(Chunk).where(Chunk.document_id == row.id))
    commitment = make_commitment(db, account)
    link_evidence(db, commitment, chunk, "supporting")
    return row, chunk, commitment


def test_content_change_with_referenced_chunk_and_acl_revocation_blocks_content_but_revokes_access(db):
    org, account, alice, bob, product = _setup(db)
    row, chunk, commitment = _make_referenced_document(db, org, account)

    doc_v2 = _doc(content="new content", acl=NormalizedAcl(users=[], groups=[]))  # revoke product
    result = ingest_document(db, org.id, doc_v2)

    assert result.outcome == "blocked"
    assert "referenced by commitment evidence" in result.reason

    reloaded = db.get(SourceDocument, row.id)
    assert reloaded.content_hash == row.content_hash  # content untouched
    remaining_chunks = db.scalars(select(Chunk).where(Chunk.document_id == row.id)).all()
    assert [c.id for c in remaining_chunks] == [chunk.id]  # old chunk preserved
    assert db.scalar(select(CommitmentEvidence).where(CommitmentEvidence.chunk_id == chunk.id)) is not None

    bob_ctx = get_user_context(db, bob.id)
    assert get_permitted_chunks(db, bob_ctx, account.id) == []  # revoked immediately


def test_content_change_with_referenced_chunk_and_new_principal_withholds_new_grant(db):
    org, account, alice, bob, product = _setup(db)
    row, chunk, commitment = _make_referenced_document(db, org, account)

    doc_v2 = _doc(content="new content", acl=NormalizedAcl(users=["alice@x.example"], groups=["product"]))
    result = ingest_document(db, org.id, doc_v2)

    assert result.outcome == "blocked"
    alice_ctx = get_user_context(db, alice.id)
    assert get_permitted_chunks(db, alice_ctx, account.id) == []  # new grant withheld

    reloaded = db.get(SourceDocument, row.id)
    assert reloaded.content_hash == row.content_hash


def test_content_change_with_referenced_chunk_one_removal_one_addition(db):
    org, account, alice, bob, product = _setup(db)
    row, chunk, commitment = _make_referenced_document(db, org, account)

    doc_v2 = _doc(content="new content", acl=NormalizedAcl(users=["alice@x.example"], groups=[]))
    result = ingest_document(db, org.id, doc_v2)

    assert result.outcome == "blocked"
    bob_ctx = get_user_context(db, bob.id)
    alice_ctx = get_user_context(db, alice.id)
    assert get_permitted_chunks(db, bob_ctx, account.id) == []  # product removal applied
    assert get_permitted_chunks(db, alice_ctx, account.id) == []  # alice addition withheld

    remaining_chunks = db.scalars(select(Chunk).where(Chunk.document_id == row.id)).all()
    assert [c.id for c in remaining_chunks] == [chunk.id]
    assert db.scalar(select(CommitmentEvidence).where(CommitmentEvidence.chunk_id == chunk.id)) is not None


def test_unresolved_new_principal_does_not_block_safe_revocation(db):
    """Correction #1's core scenario: existing group grant must be
    revoked immediately even though a new, unresolvable principal is
    declared alongside its removal — and even when content is unchanged.
    """
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(acl=NormalizedAcl(users=[], groups=["product"]))
    first = ingest_document(db, org.id, doc_v1)

    doc_v2 = _doc(acl=NormalizedAcl(users=["ghost@x.example"], groups=[]))
    result = ingest_document(db, org.id, doc_v2)

    assert result.outcome == "blocked"
    assert "ghost@x.example" in result.reason
    bob_ctx = get_user_context(db, bob.id)
    assert get_permitted_chunks(db, bob_ctx, account.id) == []  # product revoked despite the block

    grants = db.scalars(select(DocumentUserAcl).where(DocumentUserAcl.document_id == first.document_id)).all()
    assert grants == []  # ghost user never granted anything


def test_unresolved_new_principal_keeps_existing_grant_while_revoking_another(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(acl=NormalizedAcl(users=["alice@x.example"], groups=["product"]))
    first = ingest_document(db, org.id, doc_v1)

    # keep alice, drop product, add an unresolvable new group
    doc_v3 = NormalizedDocument(
        external_id=doc_v1.external_id, source="support", account_slug="acme-corp", title="Title",
        content="Content", occurred_at=doc_v1.occurred_at, sensitivity="internal",
        acl=NormalizedAcl(users=["alice@x.example"], groups=["ghost-group"]),
    )
    result = ingest_document(db, org.id, doc_v3)

    assert result.outcome == "blocked"
    alice_ctx = get_user_context(db, alice.id)
    bob_ctx = get_user_context(db, bob.id)
    assert len(get_permitted_chunks(db, alice_ctx, account.id)) == 1  # alice's grant untouched
    assert get_permitted_chunks(db, bob_ctx, account.id) == []  # product revoked

    grants = db.scalars(select(DocumentGroupAcl).where(DocumentGroupAcl.document_id == first.document_id)).all()
    assert grants == []  # ghost-group never granted anything


def test_acl_none_is_a_plain_rejection_with_no_inferred_revocation(db):
    org, account, alice, bob, product = _setup(db)
    doc_v1 = _doc(acl=NormalizedAcl(users=[], groups=["product"]))
    first = ingest_document(db, org.id, doc_v1)

    doc_v2 = _doc(acl=None)
    result = ingest_document(db, org.id, doc_v2)

    assert result.outcome == "rejected"
    bob_ctx = get_user_context(db, bob.id)
    assert len(get_permitted_chunks(db, bob_ctx, account.id)) == 1  # untouched, not revoked
