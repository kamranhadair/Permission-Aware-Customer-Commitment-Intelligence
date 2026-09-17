"""Explicit backfill for chunks.embedding. No trigger from the ingestion
CLI, no background worker — a manually-run step, matching the project's
"prefer an explicit indexing/backfill command over background workers"
convention.

    python -m app.retrieval.embed_missing [--batch-size N]

Picks up every chunk with embedding IS NULL: brand-new chunks from a fresh
ingestion, and replacement chunks from a content-changing re-ingestion
(Milestone 3's delete+reinsert already leaves these NULL) — both are
handled identically, no special-casing needed.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Chunk
from app.retrieval.embeddings import BgeEmbeddingProvider, EmbeddingProvider

DEFAULT_BATCH_SIZE = 64


def embed_missing_chunks(session: Session, provider: EmbeddingProvider, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Embeds every chunk with embedding IS NULL, in batches, committing per
    batch. Returns the total number embedded. Shared by this CLI and the
    Milestone 7 demo seed (backend/src/app/demo/seed.py) — both need the
    exact same "embed whatever isn't embedded yet" behavior, not a second
    implementation of it.
    """
    total = 0
    while True:
        chunks = list(
            session.scalars(
                select(Chunk).where(Chunk.embedding.is_(None)).order_by(Chunk.id).limit(batch_size)
            )
        )
        if not chunks:
            break
        embeddings = provider.embed_documents([chunk.content for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        session.commit()
        total += len(chunks)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.retrieval.embed_missing")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)

    provider = BgeEmbeddingProvider()
    session = SessionLocal()
    try:
        total = embed_missing_chunks(session, provider, args.batch_size)
    finally:
        session.close()

    print(f"done: {total} chunk(s) embedded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
