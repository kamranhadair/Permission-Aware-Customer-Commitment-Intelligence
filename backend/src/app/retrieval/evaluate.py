"""Small retrieval-quality/eval script — manual, not part of `pytest`/CI.
Requires the `embeddings` extra (real BAAI/bge-small-en-v1.5 provider); the
paraphrase/semantic golden queries are meaningless against
FakeEmbeddingProvider.

    python -m app.retrieval.evaluate

Seeds a dedicated "Retrieval Eval Org" (never touches real org data),
ingests the three Milestone 3 fixture sources, embeds every chunk, runs
each query in fixtures/retrieval_eval/golden_queries.json, and reports
Recall@5, Recall@10, MRR per category plus the one hard security gate:
unauthorized_candidate_count == 0 across every query/persona pair. Not
idempotent — run against a scratch database, not the dev database.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.models import Account, Chunk, Group, GroupMembership, Organization, SourceDocument, User
from app.permissions.resolver import get_permitted_document_ids, get_user_context
from app.retrieval.embeddings import BgeEmbeddingProvider
from app.retrieval.service import retrieve

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES = BACKEND_DIR / "fixtures"
GOLDEN_QUERIES = BACKEND_DIR / "fixtures" / "retrieval_eval" / "golden_queries.json"


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _seed(session) -> tuple[Organization, dict[str, User]]:
    org = Organization(name="Retrieval Eval Org")
    session.add(org)
    session.flush()

    for slug in ("acme-corp", "globex-inc"):
        session.add(Account(org_id=org.id, slug=slug, name=slug))
    session.flush()

    users = {}
    for name in ("alice", "bob", "carol"):
        user = User(org_id=org.id, email=f"{name}@vendor.example", display_name=name)
        session.add(user)
        users[name] = user
    session.flush()

    groups = {}
    for name in ("account-management", "product", "exec"):
        group = Group(org_id=org.id, name=name)
        session.add(group)
        groups[name] = group
    session.flush()

    session.add_all(
        [
            GroupMembership(user_id=users["alice"].id, group_id=groups["account-management"].id),
            GroupMembership(user_id=users["bob"].id, group_id=groups["product"].id),
            GroupMembership(user_id=users["carol"].id, group_id=groups["product"].id),
            GroupMembership(user_id=users["carol"].id, group_id=groups["exec"].id),
        ]
    )
    session.commit()
    return org, users


def _ingest_fixtures(session, org_id: int) -> None:
    support_docs, _ = support_parser.parse(_load(FIXTURES / "support" / "tickets.json"))
    call_docs, _ = calls_parser.parse(_load(FIXTURES / "calls" / "calls.json"))
    slack_docs, _ = slack_parser.parse(
        _load(FIXTURES / "slack" / "channels.json"), _load(FIXTURES / "slack" / "messages.json")
    )
    ingest_batch(session, org_id, support_docs + call_docs + slack_docs)


def _embed_all(session, provider: BgeEmbeddingProvider) -> None:
    chunks = list(session.scalars(select(Chunk)))
    if not chunks:
        return
    embeddings = provider.embed_documents([c.content for c in chunks])
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
    session.commit()


def _expected_chunk_ids(session, account_slug: str, expected: list[dict]) -> set[int]:
    ids: set[int] = set()
    for item in expected:
        rows = session.execute(
            select(Chunk.id)
            .join(SourceDocument, SourceDocument.id == Chunk.document_id)
            .join(Account, Account.id == SourceDocument.account_id)
            .where(
                Account.slug == account_slug,
                SourceDocument.source == item["source"],
                SourceDocument.external_id == item["external_id"],
            )
        ).all()
        ids.update(r.id for r in rows)
    return ids


def main() -> int:
    session = SessionLocal()
    provider = BgeEmbeddingProvider()
    try:
        org, users = _seed(session)
        _ingest_fixtures(session, org.id)
        _embed_all(session, provider)

        golden = _load(GOLDEN_QUERIES)["queries"]
        per_category: dict[str, list[float]] = {}
        unauthorized_candidates = 0

        for item in golden:
            persona = users[item["persona"]]
            user_ctx = get_user_context(session, persona.id)
            permitted_docs = get_permitted_document_ids(session, user_ctx)

            result = retrieve(session, user_ctx, provider, item["query"], account_slug=item["account_slug"])
            assert result is not None

            for hit in result.hits:
                if hit.document_id not in permitted_docs:
                    unauthorized_candidates += 1
            for trace_list in (result.trace.lexical_candidates, result.trace.vector_candidates):
                for candidate in trace_list:
                    chunk = session.get(Chunk, candidate.chunk_id)
                    if chunk is not None and chunk.document_id not in permitted_docs:
                        unauthorized_candidates += 1

            expected_ids = _expected_chunk_ids(session, item["account_slug"], item.get("expected", []))
            returned_ids = [hit.chunk_id for hit in result.hits]

            recall_5 = _recall_at_k(expected_ids, returned_ids, 5)
            recall_10 = _recall_at_k(expected_ids, returned_ids, 10)
            mrr = _mrr(expected_ids, returned_ids)

            category = item["category"]
            per_category.setdefault(category, []).append((recall_5, recall_10, mrr))

            print(f"[{item['id']}] {item['category']}: recall@5={recall_5:.2f} recall@10={recall_10:.2f} mrr={mrr:.2f}")

        print()
        print("=== Per-category averages ===")
        for category, rows in per_category.items():
            n = len(rows)
            avg_r5 = sum(r[0] for r in rows) / n
            avg_r10 = sum(r[1] for r in rows) / n
            avg_mrr = sum(r[2] for r in rows) / n
            print(f"{category}: recall@5={avg_r5:.2f} recall@10={avg_r10:.2f} mrr={avg_mrr:.2f} (n={n})")

        print()
        print(f"unauthorized_candidate_count = {unauthorized_candidates}")
        assert unauthorized_candidates == 0, "SECURITY GATE FAILED: unauthorized candidate observed"
        return 0
    finally:
        session.close()


def _recall_at_k(expected: set[int], returned: list[int], k: int) -> float:
    if not expected:
        return 1.0 if not returned[:k] else 0.0  # permission-exclusion queries: nothing should be returned
    hit = len(expected & set(returned[:k]))
    return hit / len(expected)


def _mrr(expected: set[int], returned: list[int]) -> float:
    for idx, chunk_id in enumerate(returned, start=1):
        if chunk_id in expected:
            return 1.0 / idx
    return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
