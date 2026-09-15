"""Unit tests for the centralized permission resolver.

These prove the resolver's own logic in isolation from HTTP concerns.
Behavioral proof that unauthorized data can't reach a client lives in
test_accounts_api.py / test_commitments_api.py / test_chunks_api.py.
"""

from app.models import GroupMembership
from app.permissions.resolver import get_permitted_chunks, get_permitted_document_ids, get_user_context
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


def test_direct_user_acl_grants_access(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    assert get_permitted_document_ids(db, ctx, account.id) == {doc.id}


def test_group_acl_grants_access(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)

    ctx = get_user_context(db, user.id)
    assert get_permitted_document_ids(db, ctx, account.id) == {doc.id}


def test_unrelated_user_cannot_access_document(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    owner = make_user(db, org, "owner@x.com")
    grant_user_acl(db, doc, owner)
    outsider = make_user(db, org, "outsider@x.com")

    ctx = get_user_context(db, outsider.id)
    assert get_permitted_document_ids(db, ctx, account.id) == set()


def test_removing_group_membership_revokes_access(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    user = make_user(db, org, "u1@x.com")
    group = make_group(db, org, "product")
    add_membership(db, user, group)
    grant_group_acl(db, doc, group)

    ctx_before = get_user_context(db, user.id)
    assert get_permitted_document_ids(db, ctx_before, account.id) == {doc.id}

    db.query(GroupMembership).filter_by(user_id=user.id, group_id=group.id).delete()
    db.flush()

    ctx_after = get_user_context(db, user.id)
    assert get_permitted_document_ids(db, ctx_after, account.id) == set()


def test_display_role_alone_grants_no_access(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    make_document(db, account)
    user = make_user(db, org, "vp@x.com", role="VP Product")
    # No ACL grant, no group membership — only a display-only role string.

    ctx = get_user_context(db, user.id)
    assert ctx.role == "VP Product"
    assert get_permitted_document_ids(db, ctx, account.id) == set()


def test_chunk_inherits_document_permission(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    ctx = get_user_context(db, user.id)
    chunks = get_permitted_chunks(db, ctx, account.id)
    assert [c.id for c in chunks] == [chunk.id]


def test_sensitivity_label_has_no_effect_on_access(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    confidential_doc = make_document(db, account, sensitivity="confidential")
    shared_doc = make_document(db, account, sensitivity="customer_shared")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, confidential_doc, user)
    # shared_doc is "customer_shared" but has NO acl grant for this user.

    ctx = get_user_context(db, user.id)
    permitted = get_permitted_document_ids(db, ctx, account.id)

    assert permitted == {confidential_doc.id}  # permitted despite being confidential
    assert shared_doc.id not in permitted  # denied despite being customer_shared


# --- Fail-closed against malformed cross-organization relational data -----


def test_cross_org_group_membership_is_not_a_valid_principal(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acme")
    doc_a = make_document(db, account_a)
    user_a = make_user(db, org_a, "u1@a.com")
    group_b = make_group(db, org_b, "product")  # group belongs to a DIFFERENT org
    add_membership(db, user_a, group_b)  # malformed membership row
    grant_group_acl(db, doc_a, group_b)

    ctx = get_user_context(db, user_a.id)
    assert group_b.id not in ctx.group_ids
    assert get_permitted_document_ids(db, ctx, account_a.id) == set()


def test_cross_org_document_acl_grants_no_access(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acme")
    doc_a = make_document(db, account_a)
    user_a = make_user(db, org_a, "u1@a.com")
    group_a = make_group(db, org_a, "product")  # legitimate org-a group
    add_membership(db, user_a, group_a)
    group_b = make_group(db, org_b, "product")  # different org, same name
    grant_group_acl(db, doc_a, group_b)  # malformed: ACL grants to the WRONG org's group

    ctx = get_user_context(db, user_a.id)
    assert group_a.id in ctx.group_ids
    assert get_permitted_document_ids(db, ctx, account_a.id) == set()


def test_combined_cross_org_membership_and_acl_still_denied(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acme")
    doc_a = make_document(db, account_a)
    user_a = make_user(db, org_a, "u1@a.com")
    group_b = make_group(db, org_b, "product")
    add_membership(db, user_a, group_b)  # malformed membership
    grant_group_acl(db, doc_a, group_b)  # ACL granted to that same cross-org group

    ctx = get_user_context(db, user_a.id)
    assert get_permitted_document_ids(db, ctx, account_a.id) == set()
