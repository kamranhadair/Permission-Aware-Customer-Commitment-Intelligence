"""Proves lexical_search's candidate generation is permission-scoped: an
unauthorized chunk must never become a candidate, regardless of how well
it matches the query — not just be absent from a final "top-k" cut."""

from app.permissions.resolver import get_user_context
from app.retrieval.lexical import lexical_search
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


def test_permitted_lexical_match_is_returned(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="the SSO login flow keeps failing for admins")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    results = lexical_search(db, ctx, "SSO login failing")
    assert [c.chunk_id for c in results] == [chunk.id]


def test_stronger_unauthorized_match_is_never_returned_or_candidated(db):
    org = make_org(db)
    account = make_account(db, org, "acme")

    permitted_doc = make_document(db, account)
    permitted_chunk = make_chunk(db, permitted_doc, content="SSO login issue mentioned briefly")

    forbidden_doc = make_document(db, account)
    forbidden_chunk = make_chunk(
        db, forbidden_doc, content="SSO login SSO login SSO login SSO login critical outage"
    )

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, permitted_doc, user)
    # No grant on forbidden_doc — its chunk should lexically outrank the
    # permitted one, but must never appear as a candidate at all.

    ctx = get_user_context(db, user.id)
    results = lexical_search(db, ctx, "SSO login")

    chunk_ids = [c.chunk_id for c in results]
    assert forbidden_chunk.id not in chunk_ids
    assert chunk_ids == [permitted_chunk.id]


def test_group_acl_grants_lexical_visibility(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="rate limit increase requested")
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)

    ctx = get_user_context(db, user.id)
    results = lexical_search(db, ctx, "rate limit increase")
    assert [c.chunk_id for c in results] == [chunk.id]


def test_direct_user_acl_grants_lexical_visibility(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="renewal discussion notes")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    results = lexical_search(db, ctx, "renewal discussion")
    assert [c.chunk_id for c in results] == [chunk.id]


def test_revoked_document_acl_immediately_removes_chunk_from_results(db):
    from app.models import DocumentUserAcl

    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    make_chunk(db, doc, content="confidential roadmap detail")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    assert len(lexical_search(db, ctx, "confidential roadmap")) == 1

    db.query(DocumentUserAcl).filter_by(document_id=doc.id, user_id=user.id).delete()
    db.flush()

    assert lexical_search(db, ctx, "confidential roadmap") == []


def test_unauthorized_chunk_never_appears_across_multiple_accounts(db):
    org = make_org(db)
    account_a = make_account(db, org, "acme")
    account_b = make_account(db, org, "globex")
    doc_a = make_document(db, account_a)
    doc_b = make_document(db, account_b)
    chunk_a = make_chunk(db, doc_a, content="acme specific rollout notes")
    make_chunk(db, doc_b, content="globex specific rollout notes")

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc_a, user)

    ctx = get_user_context(db, user.id)
    results = lexical_search(db, ctx, "rollout notes")
    assert [c.chunk_id for c in results] == [chunk_a.id]
