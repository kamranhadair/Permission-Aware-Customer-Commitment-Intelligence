from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Chunks inherit permissions from this document; there is no chunk-level ACL.
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
