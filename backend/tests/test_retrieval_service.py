"""Tests for the retrieve() service boundary: account scoping/404 parity
with Milestone 2, trace/result field safety, permission freshness, and one
full ingestion-fixture end-to-end round trip."""

import json
from dataclasses import fields
from pathlib import Path

from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.models import GroupMembership
from app.permissions.resolver import get_user_context
from app.retrieval.embeddings import FakeEmbeddingProvider
from app.retrieval.service import retrieve
from app.retrieval.types import RetrievalHit
from tests.factories import (
    add_membership,
    grant_group_acl,
    grant_user_acl,
    make_account,
    make_chunk,
    make_document,
    make_group,
    make_org,
    make_user,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES = BACKEND_DIR / "fixtures"

PROVIDER = FakeEmbeddingProvider()


def _embed(db, chunk) -> None:
    chunk.embedding = PROVIDER.embed_documents([chunk.content])[0]
    db.flush()


# --- Account scoping / resource privacy -----------------------------------


def test_inaccessible_account_scoped_search_behaves_like_nonexistent_account(db):
    org = make_org(db)
    make_account(db, org, "acme")  # exists, but user gets no grant
    user = make_user(db, org, "u1@x.com")

    ctx = get_user_context(db, user.id)
    assert retrieve(db, ctx, PROVIDER, "anything", account_slug="acme") is None
    assert retrieve(db, ctx, PROVIDER, "anything", account_slug="does-not-exist") is None


def test_cross_org_account_search_behaves_like_nonexistent(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    make_account(db, org_b, "globex")
    user_a = make_user(db, org_a, "u1@a.com")

    ctx = get_user_context(db, user_a.id)
    assert retrieve(db, ctx, PROVIDER, "anything", account_slug="globex") is None


def test_search_all_accounts_never_reveals_an_inaccessible_account_name(db):
    org = make_org(db)
    visible_account = make_account(db, org, "acme")
    hidden_account = make_account(db, org, "globex")  # user has no permitted docs here

    visible_doc = make_document(db, visible_account)
    chunk = make_chunk(db, visible_doc, content="visible content about onboarding")
    _embed(db, chunk)
    hidden_doc = make_document(db, hidden_account)
    hidden_chunk = make_chunk(db, hidden_doc, content="onboarding content nobody should see")
    _embed(db, hidden_chunk)

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)

    ctx = get_user_context(db, user.id)
    result = retrieve(db, ctx, PROVIDER, "onboarding")
    assert result is not None

    returned_ids = {hit.chunk_id for hit in result.hits}
    assert hidden_chunk.id not in returned_ids
    assert hidden_doc.id not in {hit.document_id for hit in result.hits}
    assert result.trace.account_scope == "all"  # no per-account enumeration in the trace


def test_retrieval_hit_schema_has_no_acl_principal_fields(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="grantable evidence")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    result = retrieve(db, ctx, PROVIDER, "grantable evidence", account_slug="acme")
    assert result is not None and result.hits

    field_names = {f.name for f in fields(RetrievalHit)}
    forbidden = {"allowed_users", "allowed_groups", "acl", "sensitivity"}
    assert not (field_names & forbidden)


# --- Permission freshness --------------------------------------------------


def test_removing_group_membership_immediately_stops_matching_that_groups_chunks(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="roadmap detail for product group only")
    _embed(db, chunk)
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)

    # A second, always-permitted document keeps the account itself visible
    # to this user after the group grant below is revoked — isolating the
    # assertion to "this chunk disappears," not "the whole account 404s."
    anchor_doc = make_document(db, account)
    anchor_chunk = make_chunk(db, anchor_doc, content="an unrelated always-visible anchor document")
    _embed(db, anchor_chunk)
    grant_user_acl(db, anchor_doc, user)

    ctx_before = get_user_context(db, user.id)
    result_before = retrieve(db, ctx_before, PROVIDER, "roadmap detail", account_slug="acme")
    assert result_before is not None
    assert chunk.id in {h.chunk_id for h in result_before.hits}

    db.query(GroupMembership).filter_by(user_id=user.id, group_id=group.id).delete()
    db.flush()

    ctx_after = get_user_context(db, user.id)
    result_after = retrieve(db, ctx_after, PROVIDER, "roadmap detail", account_slug="acme")
    assert result_after is not None
    assert chunk.id not in {h.chunk_id for h in result_after.hits}


def test_revoking_document_acl_immediately_stops_returning_its_chunks(db):
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
    result_before = retrieve(db, ctx, PROVIDER, "confidential contract terms", account_slug="acme")
    assert result_before is not None
    assert chunk.id in {h.chunk_id for h in result_before.hits}

    from app.models import DocumentUserAcl

    db.query(DocumentUserAcl).filter_by(document_id=doc.id, user_id=user.id).delete()
    db.flush()

    result_after = retrieve(db, ctx, PROVIDER, "confidential contract terms", account_slug="acme")
    assert result_after is not None
    assert chunk.id not in {h.chunk_id for h in result_after.hits}


# --- End-to-end: real Milestone 3 fixtures through ingestion + retrieval --


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def test_ingested_fixture_data_authorized_gets_hit_unauthorized_does_not(db):
    org = make_org(db, "Vendor Org")
    make_account(db, org, "acme-corp")
    make_account(db, org, "globex-inc")

    alice = make_user(db, org, "alice@vendor.example")
    bob = make_user(db, org, "bob@vendor.example")

    account_management = make_group(db, org, "account-management")
    product = make_group(db, org, "product")
    make_group(db, org, "exec")  # must exist for C-ACME-INTERNAL's ACL (product+exec) to resolve at all
    add_membership(db, alice, account_management)
    add_membership(db, bob, product)

    support_docs, _ = support_parser.parse(_load(FIXTURES / "support" / "tickets.json"))
    call_docs, _ = calls_parser.parse(_load(FIXTURES / "calls" / "calls.json"))
    slack_docs, _ = slack_parser.parse(
        _load(FIXTURES / "slack" / "channels.json"), _load(FIXTURES / "slack" / "messages.json")
    )
    ingest_batch(db, org.id, support_docs + call_docs + slack_docs)

    from sqlalchemy import select

    from app.models import Chunk

    for chunk in db.scalars(select(Chunk)):
        chunk.embedding = PROVIDER.embed_documents([chunk.content])[0]
    db.flush()

    alice_ctx = get_user_context(db, alice.id)
    bob_ctx = get_user_context(db, bob.id)

    # The SSO ticket is alice's direct-ACL evidence.
    alice_result = retrieve(db, alice_ctx, PROVIDER, "SSO login fails for admins", account_slug="acme-corp")
    assert alice_result is not None
    alice_titles = {hit.title for hit in alice_result.hits}
    assert "SSO login intermittently fails for Acme admins" in alice_titles

    # The product-only Slack thread must never reach alice, even under a
    # query drawn straight from its text.
    exploratory_result = retrieve(
        db, alice_ctx, PROVIDER, "November SSO date exploratory Product approval", account_slug="acme-corp"
    )
    assert exploratory_result is not None
    assert not any(t.startswith("Slack thread in #product-acme-internal") for t in {h.title for h in exploratory_result.hits})

    # bob (product) CAN see it.
    bob_result = retrieve(
        db, bob_ctx, PROVIDER, "November SSO date exploratory Product approval", account_slug="acme-corp"
    )
    assert bob_result is not None
    assert any(t.startswith("Slack thread in #product-acme-internal") for t in {h.title for h in bob_result.hits})
