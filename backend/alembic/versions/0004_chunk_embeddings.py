"""add pgvector extension and chunks.embedding column

Revision ID: 0004_chunk_embeddings
Revises: 0003_chunks_fulltext_index
Create Date: 2026-09-16 00:00:01.000000

`chunks.embedding` is nullable: every chunk that predates this migration
(and every new/replacement chunk from Milestone 3 ingestion, which never
sets it) starts unembedded. `app.retrieval.embed_missing` is the explicit,
manually-run backfill step — there is no trigger here and no background
worker. 384 is BAAI/bge-small-en-v1.5's native output dimension (see
app.models.chunk.EMBEDDING_DIMENSIONS) — one embedding model for this
prototype, not a versioned/configurable value.

No ANN index (HNSW/IVFFlat) is created — Milestone 4 uses exact
(brute-force) nearest-neighbor search so the permission predicate in the
retrieval query's WHERE clause is evaluated against literal rows before
any distance ranking, with no approximate index traversal step that could
ever surface an unauthorized row as a candidate. See docs/architecture.md /
the Milestone 4 design notes for the full trade-off discussion.
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "0004_chunk_embeddings"
down_revision: Union[str, Sequence[str], None] = "0003_chunks_fulltext_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "embedding")
    # Extension is left installed on downgrade — other objects/tools in the
    # database may depend on it, and dropping it is not this migration's
    # to decide.
