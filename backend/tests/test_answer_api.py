"""HTTP-level proof for POST /answer, mirroring test_search_api.py's
conventions. Both the embedding provider and the answer generator
dependencies are overridden with fakes so this suite never loads the real
BGE model or calls the real Anthropic API."""

import pytest

from app.generation.provider import FakeAnswerGenerator
from app.generation.types import Claim, GeneratedAnswer
from app.main import app
from app.retrieval.embeddings import FakeEmbeddingProvider
from app.routers.answer import get_answer_generator
from app.routers.search import get_embedding_provider
from tests.factories import grant_user_acl, make_account, make_chunk, make_document, make_org, make_user


def _override_generator(generator):
    app.dependency_overrides[get_answer_generator] = lambda: generator


@pytest.fixture()
def client(client):
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_embedding_provider, None)
        app.dependency_overrides.pop(get_answer_generator, None)


def test_answer_requires_x_user_id(client):
    resp = client.post("/answer", json={"query": "anything", "account_slug": "acme"})
    assert resp.status_code == 401


def test_answer_404s_for_nonexistent_account(db, client):
    org = make_org(db)
    user = make_user(db, org, "u1@x.com")
    _override_generator(FakeAnswerGenerator())

    resp = client.post(
        "/answer", json={"query": "q", "account_slug": "does-not-exist"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 404


def test_answer_404s_for_inaccessible_account(db, client):
    org = make_org(db)
    make_account(db, org, "acme")  # exists, but user has no permitted documents
    user = make_user(db, org, "u1@x.com")
    _override_generator(FakeAnswerGenerator())

    resp = client.post("/answer", json={"query": "q", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 404


def test_answer_502s_on_generation_failure(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    make_chunk(db, doc, content="some evidence")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    _override_generator(FakeAnswerGenerator(raise_failure=True))

    resp = client.post(
        "/answer", json={"query": "some evidence", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Answer generation failed"}


def test_answer_200_insufficient_evidence(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)  # permitted, zero chunks -> zero-context short circuit
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    _override_generator(FakeAnswerGenerator())

    resp = client.post("/answer", json={"query": "q", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "insufficient_evidence"
    assert body["citations"] == []


def test_answer_200_answered_full_round_trip(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc, content="SSO login fails for admins")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)

    def responder(query, context):
        e1 = context.evidence[0].citation_id
        return GeneratedAnswer(status="answered", claims=[Claim(text="SSO fails.", citation_ids=[e1], claim_type="evidence")])

    _override_generator(FakeAnswerGenerator(respond_with=responder))

    resp = client.post(
        "/answer", json={"query": "SSO login fails", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answered"
    assert body["citations"][0]["chunk_id"] == chunk.id
    assert "[E1]" in body["answer"]


def test_answer_response_has_no_acl_or_debug_fields(db, client):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    make_chunk(db, doc, content="grantable evidence")
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    _override_generator(FakeAnswerGenerator())  # default -> insufficient_evidence, still full response shape

    resp = client.post(
        "/answer", json={"query": "grantable evidence", "account_slug": "acme"}, headers={"X-User-Id": str(user.id)}
    )
    assert resp.status_code == 200
    body = resp.json()

    forbidden_top_level = {"allowed_users", "allowed_groups", "acl", "sensitivity", "conflict_detected"}
    assert not (set(body.keys()) & forbidden_top_level)
    for citation in body["citations"]:
        assert not (set(citation.keys()) & {"allowed_users", "allowed_groups", "acl", "sensitivity"})
    trace_keys = set(body["trace"].keys())
    assert not (trace_keys & {"allowed_users", "allowed_groups", "acl", "hidden_conflict_count", "permission_filter_count"})
    assert not any("filtered" in key.lower() for key in trace_keys)
    assert "prompt" not in trace_keys and "raw_prompt" not in trace_keys
