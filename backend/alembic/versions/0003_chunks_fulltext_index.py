"""add full-text search index on chunks.content

Revision ID: 0003_chunks_fulltext_index
Revises: 0002_ingestion_identity
Create Date: 2026-09-16 00:00:00.000000

A GIN index over the `to_tsvector('english', content)` expression, not a
stored `tsvector` column: nothing to backfill and nothing that can go
stale. Postgres recomputes the expression from `content` on every write, so
Milestone 3's delete+reinsert chunk-replacement behavior is transparently
covered with no migration-side data movement needed.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003_chunks_fulltext_index"
down_revision: Union[str, Sequence[str], None] = "0002_ingestion_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_chunks_content_fts ON chunks "
        "USING GIN (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_chunks_content_fts")
