from tests.factories import grant_user_acl, make_account, make_document, make_org, make_user


def test_list_accounts_returns_only_accounts_with_permitted_documents(db, client):
    org = make_org(db)
    visible_account = make_account(db, org, "acme")
    hidden_account = make_account(db, org, "beta")  # same org, but nothing grants this user access
    visible_doc = make_document(db, visible_account)
    make_document(db, hidden_account)

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)

    resp = client.get("/accounts", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert [a["id"] for a in resp.json()] == ["acme"]


def test_list_accounts_returns_empty_when_no_documents_are_permitted(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    make_document(db, account)
    user = make_user(db, org, "u1@x.com")  # no ACL grants at all

    resp = client.get("/accounts", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_same_org_account_with_no_permitted_docs_returns_404(db, client):
    org = make_org(db)
    account = make_account(db, org, "beta")
    make_document(db, account)  # exists, but user has no ACL to it
    user = make_user(db, org, "u1@x.com")

    resp = client.get(f"/accounts/{account.slug}", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_cross_org_account_returns_404(db, client):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_b = make_account(db, org_b, "beta")
    make_document(db, account_b)
    user_a = make_user(db, org_a, "u1@a.com")

    resp = client.get(f"/accounts/{account_b.slug}", headers={"X-User-Id": str(user_a.id)})
    assert resp.status_code == 404


def test_nonexistent_account_returns_404(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")

    resp = client.get("/accounts/does-not-exist", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_inaccessible_and_nonexistent_accounts_are_indistinguishable(db, client):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")

    same_org_no_access = make_account(db, org_a, "no-access")
    make_document(db, same_org_no_access)

    cross_org_account = make_account(db, org_b, "cross-org")
    make_document(db, cross_org_account)

    user = make_user(db, org_a, "u1@a.com")

    r1 = client.get("/accounts/no-access", headers={"X-User-Id": str(user.id)})
    r2 = client.get("/accounts/cross-org", headers={"X-User-Id": str(user.id)})
    r3 = client.get("/accounts/does-not-exist", headers={"X-User-Id": str(user.id)})

    assert r1.status_code == r2.status_code == r3.status_code == 404
    assert r1.json() == r2.json() == r3.json()


def test_permitted_user_can_access_visible_account(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    resp = client.get("/accounts/acme", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert resp.json() == {"id": "acme", "name": "acme"}
