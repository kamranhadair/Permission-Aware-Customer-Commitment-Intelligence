from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        CheckConstraint(
            "source IN ('call','support','jira','slack','contract','crm')",
            name="ck_source_documents_source",
        ),
        CheckConstraint(
            "sensitivity IN ('internal','confidential','customer_shared')",
            name="ck_source_documents_sensitivity",
        ),
        CheckConstraint(
            "(external_id IS NULL AND content_hash IS NULL) OR "
            "(external_id IS NOT NULL AND content_hash IS NOT NULL)",
            name="ck_source_documents_ingestion_identity",
        ),
        UniqueConstraint(
            "account_id", "source", "external_id", name="uq_source_documents_account_source_external"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Informational/display only — never consulted for authorization.
    sensitivity: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL on both means this row predates the Milestone 3 ingestion system
    # and is not managed by source re-ingestion. Ingestion-created rows
    # always populate both; the CHECK constraint above forbids any
    # half-managed state. Postgres allows multiple NULLs under the
    # (account_id, source, external_id) unique constraint, so legacy rows
    # never collide with each other or with ingested ones.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)


class DocumentUserAcl(Base):
    __tablename__ = "document_user_acl"

    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class DocumentGroupAcl(Base):
    __tablename__ = "document_group_acl"

    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
