from tests.factories import grant_user_acl, make_account, make_chunk, make_document, make_org, make_user


def test_chunks_endpoint_returns_only_permitted_chunks(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    visible_doc = make_document(db, account)
    hidden_doc = make_document(db, account)
    make_chunk(db, visible_doc, content="visible")
    make_chunk(db, hidden_doc, content="hidden")

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)

    resp = client.get("/accounts/acme/chunks", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    assert [c["content"] for c in resp.json()] == ["visible"]


def test_chunks_endpoint_404s_when_account_not_visible(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    make_document(db, account)  # exists, but nothing grants this user access
    user = make_user(db, org, "u1@x.com")

    resp = client.get("/accounts/acme/chunks", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_chunks_endpoint_404s_for_nonexistent_account(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")

    resp = client.get("/accounts/does-not-exist/chunks", headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404
