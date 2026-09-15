from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "sequence", name="uq_chunks_document_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Chunks inherit permissions from this document; there is no chunk-level ACL.
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 0-indexed position within the document, so display/retrieval order
    # doesn't rely on insertion order once chunks are replaced on re-ingestion.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
