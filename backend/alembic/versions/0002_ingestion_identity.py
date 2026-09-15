"""add ingestion identity columns (external_id, content_hash, chunk sequence)

Revision ID: 0002_ingestion_identity
Revises: 3715d9011473
Create Date: 2026-09-15 00:00:00.000000

Adds the columns Milestone 3 ingestion needs to identify and order rows it
manages, without requiring a reset of a database that already has
Milestone 2 rows in it:

- source_documents.external_id / content_hash are added NULLable. NULL on
  both means "this row predates ingestion and is not source-managed" — no
  fake external id or hash is fabricated for legacy rows. A CHECK
  constraint forbids the half-managed states (one NULL, one not).
- chunks.sequence is added NULLable, backfilled deterministically from
  existing chunk.id order per document, then tightened to NOT NULL with a
  UNIQUE(document_id, sequence) constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_ingestion_identity"
down_revision: Union[str, Sequence[str], None] = "3715d9011473"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_documents", sa.Column("external_id", sa.String(), nullable=True))
    op.add_column("source_documents", sa.Column("content_hash", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_source_documents_ingestion_identity",
        "source_documents",
        "(external_id IS NULL AND content_hash IS NULL) OR "
        "(external_id IS NOT NULL AND content_hash IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_source_documents_account_source_external",
        "source_documents",
        ["account_id", "source", "external_id"],
    )

    op.add_column("chunks", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY id) - 1 AS rn
            FROM chunks
        )
        UPDATE chunks SET sequence = ranked.rn
        FROM ranked
        WHERE chunks.id = ranked.id
        """
    )
    op.alter_column("chunks", "sequence", nullable=False)
    op.create_unique_constraint("uq_chunks_document_sequence", "chunks", ["document_id", "sequence"])


def downgrade() -> None:
    op.drop_constraint("uq_chunks_document_sequence", "chunks", type_="unique")
    op.drop_column("chunks", "sequence")

    op.drop_constraint("uq_source_documents_account_source_external", "source_documents", type_="unique")
    op.drop_constraint("ck_source_documents_ingestion_identity", "source_documents", type_="check")
    op.drop_column("source_documents", "content_hash")
    op.drop_column("source_documents", "external_id")
