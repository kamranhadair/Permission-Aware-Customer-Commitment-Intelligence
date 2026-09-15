"""Cross-organization access must be impossible, even when an id from
another org is supplied directly (an attacker who has learned/guessed a
real id from a different tenant)."""

from app.permissions.resolver import get_permitted_account_ids, get_permitted_document_ids, get_user_context
from tests.factories import grant_user_acl, make_account, make_document, make_org, make_user


def test_cross_org_document_id_probe_returns_nothing(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_b = make_account(db, org_b, "beta")
    doc_b = make_document(db, account_b)
    user_a = make_user(db, org_a, "u1@a.com")
    grant_user_acl(db, doc_b, user_a)  # even a (malformed) direct ACL grant across orgs

    ctx = get_user_context(db, user_a.id)
    assert get_permitted_document_ids(db, ctx, account_b.id) == set()
    assert get_permitted_account_ids(db, ctx) == set()


def test_cross_org_account_id_probe_returns_nothing(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_b = make_account(db, org_b, "beta")
    make_document(db, account_b)
    user_a = make_user(db, org_a, "u1@a.com")

    ctx = get_user_context(db, user_a.id)
    assert get_permitted_document_ids(db, ctx, account_b.id) == set()
