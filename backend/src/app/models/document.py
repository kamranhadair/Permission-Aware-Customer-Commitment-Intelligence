from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Informational/display only — never consulted for authorization.
    sensitivity: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentUserAcl(Base):
    __tablename__ = "document_user_acl"

    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class DocumentGroupAcl(Base):
    __tablename__ = "document_group_acl"

    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
