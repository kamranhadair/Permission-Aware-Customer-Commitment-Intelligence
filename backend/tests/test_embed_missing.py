"""app.retrieval.embed_missing.embed_missing_chunks: the org_id scope used
by the Milestone 7 demo seed must be enforced in the SQL WHERE clause, not
by loading every chunk and filtering in Python — and the CLI's existing
global-backfill default (org_id=None) must be unchanged.
"""

from app.retrieval.embed_missing import embed_missing_chunks
from app.retrieval.embeddings import FakeEmbeddingProvider
from tests.factories import make_account, make_chunk, make_document, make_org


def test_org_scoped_call_embeds_only_that_orgs_chunks(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acct-a")
    account_b = make_account(db, org_b, "acct-b")
    chunk_a = make_chunk(db, make_document(db, account_a), content="a")
    chunk_b = make_chunk(db, make_document(db, account_b), content="b")

    total = embed_missing_chunks(db, FakeEmbeddingProvider(), org_id=org_a.id)

    db.refresh(chunk_a)
    db.refresh(chunk_b)
    assert total == 1
    assert chunk_a.embedding is not None
    assert chunk_b.embedding is None


def test_global_call_without_org_id_still_embeds_every_org(db):
    org_a = make_org(db, "Org A")
    org_b = make_org(db, "Org B")
    account_a = make_account(db, org_a, "acct-a")
    account_b = make_account(db, org_b, "acct-b")
    chunk_a = make_chunk(db, make_document(db, account_a), content="a")
    chunk_b = make_chunk(db, make_document(db, account_b), content="b")

    total = embed_missing_chunks(db, FakeEmbeddingProvider())

    db.refresh(chunk_a)
    db.refresh(chunk_b)
    assert total == 2
    assert chunk_a.embedding is not None
    assert chunk_b.embedding is not None
