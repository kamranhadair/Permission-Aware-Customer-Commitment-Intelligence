"""Evaluation-only, FK-safe deletion of exactly the rows a Milestone 6
evaluation run seeded under specific organization ids. Production models
gain no cascade behavior for this — deletion order is handled explicitly
here, in dependency order, using ordinary parameterized `DELETE ... WHERE
id IN (...)` statements scoped to real ids resolved from the given org
ids, never to a broader condition.

Only ever invoked for a runner-owned session (a standalone `python -m
app.evaluation.run` invocation) — never for a caller-supplied session, where
the caller (a pytest fixture's SAVEPOINT rollback) already owns cleanup/
isolation and a destructive delete here would be both redundant and wrong
(it would commit through the test's isolation boundary).
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Chunk,
    Commitment,
    CommitmentEvidence,
    DocumentGroupAcl,
    DocumentUserAcl,
    Group,
    GroupMembership,
    Organization,
    SourceDocument,
    User,
)


def cleanup_eval_orgs(session: Session, org_ids: list[int]) -> None:
    """Deletes every row seeded under `org_ids` — and nothing else — in FK
    order, then commits. Safe to call after a failed/partial run: every
    delete is scoped to ids actually resolved from `org_ids`, so a run that
    failed after only partially seeding still cleans up exactly what it
    created, no more and no less."""
    if not org_ids:
        return

    account_ids = list(session.scalars(select(Account.id).where(Account.org_id.in_(org_ids))))
    document_ids = list(
        session.scalars(select(SourceDocument.id).where(SourceDocument.account_id.in_(account_ids)))
    ) if account_ids else []
    commitment_ids = list(
        session.scalars(select(Commitment.id).where(Commitment.account_id.in_(account_ids)))
    ) if account_ids else []
    user_ids = list(session.scalars(select(User.id).where(User.org_id.in_(org_ids))))
    group_ids = list(session.scalars(select(Group.id).where(Group.org_id.in_(org_ids))))

    if commitment_ids:
        session.execute(delete(CommitmentEvidence).where(CommitmentEvidence.commitment_id.in_(commitment_ids)))
        session.execute(delete(Commitment).where(Commitment.id.in_(commitment_ids)))
    if document_ids:
        session.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))
        session.execute(delete(DocumentUserAcl).where(DocumentUserAcl.document_id.in_(document_ids)))
        session.execute(delete(DocumentGroupAcl).where(DocumentGroupAcl.document_id.in_(document_ids)))
        session.execute(delete(SourceDocument).where(SourceDocument.id.in_(document_ids)))
    if user_ids:
        session.execute(delete(GroupMembership).where(GroupMembership.user_id.in_(user_ids)))
    if group_ids:
        session.execute(delete(Group).where(Group.id.in_(group_ids)))
    if user_ids:
        session.execute(delete(User).where(User.id.in_(user_ids)))
    if account_ids:
        session.execute(delete(Account).where(Account.id.in_(account_ids)))
    session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
    session.commit()
    # Core bulk deletes above never touch the session's ORM identity map —
    # without this, a caller (or a test) holding a reference to one of the
    # just-deleted ORM objects would hit a surprising ObjectDeletedError on
    # its next lazy-load/refresh instead of a clean "it's gone".
    session.expire_all()
