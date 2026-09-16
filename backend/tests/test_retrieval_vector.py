"""Proves vector_search's candidate generation is permission-scoped, with
hand-constructed embeddings so distance relationships are fully known
(rather than relying on FakeEmbeddingProvider's hash-based output to be
"close" for any particular pair of texts)."""

import math

from app.permissions.resolver import get_user_context
from app.retrieval.embeddings import EMBEDDING_DIMENSIONS
from app.retrieval.vector import vector_search
from tests.factories import (
    grant_user_acl,
    make_account,
    make_chunk,
    make_document,
    make_org,
    make_user,
)

DIM = EMBEDDING_DIMENSIONS


def _basis(index: int) -> list[float]:
    v = [0.0] * DIM
    v[index] = 1.0
    return v


def _near_basis(index: int, noise: float) -> list[float]:
    v = [noise] * DIM
    v[index] = 1.0
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def test_permitted_nearest_vector_is_returned(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    chunk = make_chunk(db, doc)
    chunk.embedding = _basis(0)
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    db.flush()

    ctx = get_user_context(db, user.id)
    results = vector_search(db, ctx, _basis(0))
    assert [c.chunk_id for c in results] == [chunk.id]


def test_mathematically_closer_unauthorized_vector_is_never_returned(db):
    org = make_org(db)
    account = make_account(db, org, "acme")

    permitted_doc = make_document(db, account)
    permitted_chunk = make_chunk(db, permitted_doc)
    permitted_chunk.embedding = _near_basis(0, noise=0.05)  # close, but not exact

    forbidden_doc = make_document(db, account)
    forbidden_chunk = make_chunk(db, forbidden_doc)
    forbidden_chunk.embedding = _basis(0)  # exact match to the query — mathematically closer

    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, permitted_doc, user)
    db.flush()

    ctx = get_user_context(db, user.id)
    results = vector_search(db, ctx, _basis(0))

    chunk_ids = [c.chunk_id for c in results]
    assert forbidden_chunk.id not in chunk_ids
    assert chunk_ids == [permitted_chunk.id]


def test_cross_org_vector_cannot_be_returned(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acme")
    account_b = make_account(db, org_b, "globex")

    doc_a = make_document(db, account_a)
    chunk_a = make_chunk(db, doc_a)
    chunk_a.embedding = _near_basis(0, noise=0.05)

    doc_b = make_document(db, account_b)
    chunk_b = make_chunk(db, doc_b)
    chunk_b.embedding = _basis(0)  # closer, but belongs to a different org entirely

    user_a = make_user(db, org_a, "u1@a.com")
    grant_user_acl(db, doc_a, user_a)
    db.flush()

    ctx = get_user_context(db, user_a.id)
    results = vector_search(db, ctx, _basis(0))

    chunk_ids = [c.chunk_id for c in results]
    assert chunk_b.id not in chunk_ids
    assert chunk_ids == [chunk_a.id]


def test_chunk_without_embedding_is_lexical_only_not_a_retrieval_failure(db):
    org = make_org(db)
    account = make_account(db, org, "acme")
    doc = make_document(db, account)
    unembedded_chunk = make_chunk(db, doc)  # embedding left NULL
    user = make_user(db, org, "u1@x.com")
    grant_user_acl(db, doc, user)
    db.flush()
    assert unembedded_chunk.embedding is None

    ctx = get_user_context(db, user.id)
    # No exception, no failure — the chunk simply never becomes a vector
    # candidate.
    results = vector_search(db, ctx, _basis(0))
    assert results == []

    from app.retrieval.lexical import lexical_search

    lexical_results = lexical_search(db, ctx, unembedded_chunk.content)
    assert [c.chunk_id for c in lexical_results] == [unembedded_chunk.id]
