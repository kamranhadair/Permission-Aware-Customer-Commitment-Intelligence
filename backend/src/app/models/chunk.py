from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# BAAI/bge-small-en-v1.5's native output dimension. One embedding model for
# this prototype (see app/retrieval/embeddings.py) — not a per-chunk
# versioned value.
EMBEDDING_DIMENSIONS = 384


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "sequence", name="uq_chunks_document_sequence"),
        # Expression index, not a stored tsvector column — nothing to
        # backfill, nothing that can go stale relative to `content`.
        Index(
            "idx_chunks_content_fts",
            text("to_tsvector('english', content)"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Chunks inherit permissions from this document; there is no chunk-level ACL.
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 0-indexed position within the document, so display/retrieval order
    # doesn't rely on insertion order once chunks are replaced on re-ingestion.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL until embed_missing backfills it (new chunk, or a re-ingested
    # replacement chunk from a content change) — such chunks are eligible
    # for lexical search but not vector search until then.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
