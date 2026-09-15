from datetime import datetime, timezone

from sqlalchemy import select

from app.ingestion.service import ingest_batch, ingest_document
from app.ingestion.types import NormalizedAcl, NormalizedDocument
from app.models import Chunk, DocumentGroupAcl, DocumentUserAcl, SourceDocument
from tests.factories import add_membership, make_account, make_group, make_org, make_user


def _doc(
    external_id="EXT-1",
    source="support",
    account_slug="acme-corp",
    title="Title",
    content="Content",
    sensitivity="internal",
    acl=NormalizedAcl(users=[], groups=[]),
    occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
):
    return NormalizedDocument(
        external_id=external_id, source=source, account_slug=account_slug, title=title, content=content,
        occurred_at=occurred_at, sensitivity=sensitivity, acl=acl,
    )


def _setup(db):
    org = make_org(db, "Org")
    account = make_account(db, org, "acme-corp")
    alice = make_user(db, org, "alice@x.example")
    group = make_group(db, org, "product")
    return org, account, alice, group


def test_normalized_document_persists_correctly(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=NormalizedAcl(users=[], groups=[]))

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "created"
    row = db.scalar(select(SourceDocument).where(SourceDocument.id == result.document_id))
    assert row.title == "Title"
    assert row.content_hash is not None
    assert row.external_id == "EXT-1"


def test_user_acl_persists_correctly(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=NormalizedAcl(users=["alice@x.example"], groups=[]))

    result = ingest_document(db, org.id, doc)

    grants = db.scalars(select(DocumentUserAcl).where(DocumentUserAcl.document_id == result.document_id)).all()
    assert [g.user_id for g in grants] == [alice.id]


def test_group_acl_persists_correctly(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=NormalizedAcl(users=[], groups=["product"]))

    result = ingest_document(db, org.id, doc)

    grants = db.scalars(select(DocumentGroupAcl).where(DocumentGroupAcl.document_id == result.document_id)).all()
    assert [g.group_id for g in grants] == [group.id]


def test_explicit_empty_acl_persists_with_zero_acl_rows(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=NormalizedAcl(users=[], groups=[]))

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "created"
    assert db.scalars(select(DocumentUserAcl).where(DocumentUserAcl.document_id == result.document_id)).all() == []
    assert db.scalars(select(DocumentGroupAcl).where(DocumentGroupAcl.document_id == result.document_id)).all() == []


def test_missing_acl_metadata_is_rejected_with_no_rows_written(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=None)

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "rejected"
    assert db.scalars(select(SourceDocument)).all() == []


def test_unresolved_acl_principal_on_create_rejects_whole_document(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=NormalizedAcl(users=["ghost@x.example"], groups=[]))

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "rejected"
    assert "ghost@x.example" in result.reason
    assert db.scalars(select(SourceDocument)).all() == []
    assert db.scalars(select(DocumentUserAcl)).all() == []


def test_unknown_account_is_rejected(db):
    org, account, alice, group = _setup(db)
    doc = _doc(account_slug="no-such-account", acl=NormalizedAcl(users=[], groups=[]))

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "rejected"
    assert db.scalars(select(SourceDocument)).all() == []


def test_cross_org_account_reference_is_rejected(db):
    org, account, alice, group = _setup(db)
    other_org = make_org(db, "Other Org")
    make_account(db, other_org, "other-account")

    doc = _doc(account_slug="other-account", acl=NormalizedAcl(users=[], groups=[]))
    result = ingest_document(db, org.id, doc)

    assert result.outcome == "rejected"


def test_invalid_sensitivity_is_rejected(db):
    org, account, alice, group = _setup(db)
    doc = _doc(sensitivity="top-secret", acl=NormalizedAcl(users=[], groups=[]))

    result = ingest_document(db, org.id, doc)

    assert result.outcome == "rejected"
    assert db.scalars(select(SourceDocument)).all() == []


def test_malformed_record_creates_no_partially_accessible_document(db):
    org, account, alice, group = _setup(db)
    doc = _doc(acl=None)

    ingest_document(db, org.id, doc)

    assert db.scalars(select(SourceDocument)).all() == []
    assert db.scalars(select(Chunk)).all() == []
    assert db.scalars(select(DocumentUserAcl)).all() == []
    assert db.scalars(select(DocumentGroupAcl)).all() == []


def test_duplicate_external_id_within_one_batch_rejects_second_occurrence(db):
    org, account, alice, group = _setup(db)
    doc_a = _doc(external_id="DUP-1", title="First")
    doc_b = _doc(external_id="DUP-1", title="Second")

    results = ingest_batch(db, org.id, [doc_a, doc_b])

    assert results[0].outcome == "created"
    assert results[1].outcome == "rejected"
    assert "duplicate" in results[1].reason
    assert len(db.scalars(select(SourceDocument)).all()) == 1
