from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Commitment(Base):
    __tablename__ = "commitments"
    __table_args__ = (
        CheckConstraint(
            "authority IN ("
            "'customer_expectation','sales_unapproved','product_target',"
            "'product_approved','contractual'"
            ")",
            name="ck_commitments_authority",
        ),
        CheckConstraint(
            "status IN ('on_track','at_risk','overdue','delivered')",
            name="ck_commitments_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    promised_by: Mapped[str] = mapped_column(String, nullable=False)
    promise_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    authority: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class CommitmentEvidence(Base):
    __tablename__ = "commitment_evidence"
    __table_args__ = (
        CheckConstraint("evidence_type IN ('supporting','conflicting')", name="ck_commitment_evidence_type"),
    )

    commitment_id: Mapped[int] = mapped_column(ForeignKey("commitments.id"), primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"), primary_key=True)
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
