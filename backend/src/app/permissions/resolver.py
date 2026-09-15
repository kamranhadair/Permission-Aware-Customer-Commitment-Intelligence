"""The single authorization chokepoint.

Routers and other callers must go through the functions in this module for
every question of "what is this user allowed to see." Nothing outside this
module should construct a query against `document_user_acl`,
`document_group_acl`, or `group_memberships`.

Tenant isolation is structural, not a duplicated `org_id` column: every
resource is reached by joining down from `accounts` (which is the only
table carrying `org_id` for the customer-data lineage), so a query that
forgets an org filter fails closed by returning nothing rather than
returning another organization's data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Account,
    Chunk,
    Commitment,
    CommitmentEvidence,
    DocumentGroupAcl,
    DocumentUserAcl,
    Group,
    GroupMembership,
    SourceDocument,
    User,
)


@dataclass(frozen=True)
class UserContext:
    id: int
    org_id: int
    email: str
    display_name: str
    role: str | None
    group_ids: frozenset[int]


@dataclass(frozen=True)
class AccountView:
    id: int
    slug: str
    name: str


@dataclass(frozen=True)
class ChunkView:
    id: int
    document_id: int
    source: str
    title: str
    sensitivity: str
    occurred_at: datetime
    content: str


@dataclass(frozen=True)
class CommitmentWithEvidence:
    id: int
    statement: str
    promised_by: str
    promise_date: date
    delivery_date: date | None
    authority: str
    status: str
    supporting: list[ChunkView]
    conflicting: list[ChunkView]


def get_user_context(db: Session, user_id: int) -> UserContext | None:
    user = db.get(User, user_id)
    if user is None:
        return None

    # Fail closed: a membership row pointing at a group that belongs to a
    # DIFFERENT org than the user (malformed/corrupt data) must never make
    # that group a valid authorization principal. Restricting this query to
    # Group.org_id == user.org_id is what makes that guarantee hold,
    # everywhere group_ids is used below.
    group_ids = set(
        db.scalars(
            select(Group.id)
            .join(GroupMembership, GroupMembership.group_id == Group.id)
            .where(GroupMembership.user_id == user.id, Group.org_id == user.org_id)
        )
    )

    return UserContext(
        id=user.id,
        org_id=user.org_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        group_ids=frozenset(group_ids),
    )


def _document_is_permitted(document_id_col: ColumnElement[int], user_ctx: UserContext) -> ColumnElement[bool]:
    """ACL-match predicate for a document id column.

    `user_ctx.group_ids` is already org-scoped (see get_user_context), so a
    document_group_acl row referencing a group from another org can never
    match here even if such a malformed row exists.
    """
    return exists(
        select(DocumentUserAcl.document_id).where(
            DocumentUserAcl.document_id == document_id_col,
            DocumentUserAcl.user_id == user_ctx.id,
        )
    ) | exists(
        select(DocumentGroupAcl.document_id).where(
            DocumentGroupAcl.document_id == document_id_col,
            DocumentGroupAcl.group_id.in_(user_ctx.group_ids),
        )
    )


def get_permitted_document_ids(db: Session, user_ctx: UserContext, account_id: int) -> set[int]:
    """Permitted document ids for one account, scoped to the caller's org.

    Starting the query at `accounts` and requiring
    `Account.org_id == user_ctx.org_id` is the tenant-isolation mechanism:
    a document belonging to another org's account is never reachable here,
    regardless of what `account_id` is passed in.
    """
    stmt = (
        select(SourceDocument.id)
        .join(Account, Account.id == SourceDocument.account_id)
        .where(Account.id == account_id, Account.org_id == user_ctx.org_id)
        .where(_document_is_permitted(SourceDocument.id, user_ctx))
    )
    return set(db.scalars(stmt))


def get_permitted_account_ids(db: Session, user_ctx: UserContext) -> set[int]:
    """Accounts visible to this user: org-scoped AND having >=1 permitted document.

    Account visibility is derived entirely from document access — there is
    no account-level ACL table. Being in the same org is necessary but not
    sufficient.
    """
    stmt = (
        select(Account.id)
        .join(SourceDocument, SourceDocument.account_id == Account.id)
        .where(Account.org_id == user_ctx.org_id)
        .where(_document_is_permitted(SourceDocument.id, user_ctx))
        .distinct()
    )
    return set(db.scalars(stmt))


def get_permitted_accounts(db: Session, user_ctx: UserContext) -> list[AccountView]:
    account_ids = get_permitted_account_ids(db, user_ctx)
    if not account_ids:
        return []
    rows = db.scalars(select(Account).where(Account.id.in_(account_ids)))
    return [AccountView(id=row.id, slug=row.slug, name=row.name) for row in rows]


def get_visible_account(db: Session, user_ctx: UserContext, account_slug: str) -> AccountView | None:
    """Resolve an account by slug, or None if it should be invisible to this user.

    Returns None uniformly for: nonexistent slug, a slug belonging to
    another org, and a same-org account the user has no permitted
    documents for. Callers must turn None into a single 404 — these three
    cases must be indistinguishable externally.
    """
    account = db.scalar(select(Account).where(Account.slug == account_slug, Account.org_id == user_ctx.org_id))
    if account is None:
        return None
    if account.id not in get_permitted_account_ids(db, user_ctx):
        return None
    return AccountView(id=account.id, slug=account.slug, name=account.name)


def _chunk_view_query():
    return select(
        Chunk.id,
        Chunk.document_id,
        SourceDocument.source,
        SourceDocument.title,
        SourceDocument.sensitivity,
        SourceDocument.occurred_at,
        Chunk.content,
    ).join(SourceDocument, SourceDocument.id == Chunk.document_id)


def get_permitted_chunks(db: Session, user_ctx: UserContext, account_id: int) -> list[ChunkView]:
    document_ids = get_permitted_document_ids(db, user_ctx, account_id)
    if not document_ids:
        return []

    rows = db.execute(_chunk_view_query().where(Chunk.document_id.in_(document_ids))).all()
    return [
        ChunkView(
            id=row.id,
            document_id=row.document_id,
            source=row.source,
            title=row.title,
            sensitivity=row.sensitivity,
            occurred_at=row.occurred_at,
            content=row.content,
        )
        for row in rows
    ]


def get_visible_commitments(db: Session, user_ctx: UserContext, account_id: int) -> list[CommitmentWithEvidence]:
    """Commitments visible to this user for one account.

    A commitment is included only if at least one of its `supporting`
    evidence chunks is permitted. `conflicting` evidence is filtered the
    same way but never gates visibility on its own, and an empty
    `conflicting` list carries no signal about whether unauthorized
    conflicting evidence exists.

    `document_ids` is already scoped to THIS account (see
    get_permitted_document_ids), so a commitment_evidence row that
    (incorrectly) links to a chunk belonging to a different account's
    document is excluded automatically — it can never make the commitment
    visible or appear in its evidence lists.
    """
    document_ids = get_permitted_document_ids(db, user_ctx, account_id)
    if not document_ids:
        return []

    commitments = list(db.scalars(select(Commitment).where(Commitment.account_id == account_id)))
    if not commitments:
        return []

    commitment_ids = [c.id for c in commitments]

    evidence_rows = db.execute(
        select(
            CommitmentEvidence.commitment_id,
            CommitmentEvidence.evidence_type,
            Chunk.id,
            Chunk.document_id,
            SourceDocument.source,
            SourceDocument.title,
            SourceDocument.sensitivity,
            SourceDocument.occurred_at,
            Chunk.content,
        )
        .join(Chunk, Chunk.id == CommitmentEvidence.chunk_id)
        .join(SourceDocument, SourceDocument.id == Chunk.document_id)
        .where(
            CommitmentEvidence.commitment_id.in_(commitment_ids),
            Chunk.document_id.in_(document_ids),
        )
    ).all()

    supporting_by_commitment: dict[int, list[ChunkView]] = {}
    conflicting_by_commitment: dict[int, list[ChunkView]] = {}
    for row in evidence_rows:
        chunk_view = ChunkView(
            id=row[2],
            document_id=row[3],
            source=row[4],
            title=row[5],
            sensitivity=row[6],
            occurred_at=row[7],
            content=row[8],
        )
        bucket = supporting_by_commitment if row.evidence_type == "supporting" else conflicting_by_commitment
        bucket.setdefault(row.commitment_id, []).append(chunk_view)

    result: list[CommitmentWithEvidence] = []
    for commitment in commitments:
        supporting = supporting_by_commitment.get(commitment.id, [])
        if not supporting:
            continue  # No permitted evidence establishes this commitment; it is not exposed.
        conflicting = conflicting_by_commitment.get(commitment.id, [])
        result.append(
            CommitmentWithEvidence(
                id=commitment.id,
                statement=commitment.statement,
                promised_by=commitment.promised_by,
                promise_date=commitment.promise_date,
                delivery_date=commitment.delivery_date,
                authority=commitment.authority,
                status=commitment.status,
                supporting=supporting,
                conflicting=conflicting,
            )
        )
    return result
