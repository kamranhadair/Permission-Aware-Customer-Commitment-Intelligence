"""HTTP-level proof for POST /search, mirroring test_chunks_api.py's
conventions. The embedding provider dependency is overridden with
FakeEmbeddingProvider so this test (like the rest of the suite) never
loads the real BGE model."""

import pytest

from app.main import app
from app.retrieval.embeddings import FakeEmbeddingProvider
from app.routers.search import get_embedding_provider
from tests.factories import grant_user_acl, make_account, make_chunk, make_document, make_org, make_user


@pytest.fixture()
def client(client):
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_embedding_provider, None)


def test_search_returns_only_permitted_results(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    visible_doc = make_document(db, account)
    hidden_doc = make_document(db, account)
    visible_chunk = make_chunk(db, visible_doc, content="visible onboarding notes")
    make_chunk(db, hidden_doc, content="hidden onboarding notes")

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, visible_doc, user)

    resp = client.post(
        "/search",
        json={"query": "onboarding notes", "account_slug": "acme"},
        headers={"X-User-Id": str(user.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    chunk_ids = {r["chunk_id"] for r in body["results"]}
    assert chunk_ids == {visible_chunk.id}


def test_search_404s_when_account_not_visible(db, client):
    org = make_org(db)
    make_account(db, org, "acme")
    user = make_user(db, org, "u1@x.com")

    resp = client.post("/search", json={"query": "anything", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_search_404s_for_nonexistent_account(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")

    resp = client.post(
        "/search", json={"query": "anything", "account_slug": "does-not-exist"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 404


def test_search_across_all_accounts_when_slug_omitted(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="cross account visible content")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    resp = client.post("/search", json={"query": "cross account visible content"}, headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    chunk_ids = {r["chunk_id"] for r in resp.json()["results"]}
    assert chunk_ids == {chunk.id}


def test_search_response_has_no_acl_principal_fields(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    make_chunk(db, doc, content="grantable evidence")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    resp = client.post(
        "/search", json={"query": "grantable evidence", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    forbidden_keys = {"allowed_users", "allowed_groups", "acl", "sensitivity"}
    for result in body["results"]:
        assert not (set(result.keys()) & forbidden_keys)
    assert "returned_chunk_ids" in body["trace"]  # trace present, but no filtered-out counts of any kind
    assert not any("filtered" in key.lower() for key in body["trace"].keys())


def test_search_requires_x_user_id(client):
    resp = client.post("/search", json={"query": "anything"})
    assert resp.status_code == 401
