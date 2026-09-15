"""Seed helpers for tests. Deliberately do not validate cross-org
consistency (e.g. a membership linking a user to another org's group) —
some tests need to construct exactly that malformed data to prove the
resolver fails closed against it.
"""

from datetime import date, datetime, timezone

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


def make_org(db: Session, name: str = "Org") -> Organization:
    org = Organization(name=name)
    db.add(org)
    db.flush()
    return org


def make_user(db: Session, org: Organization, email: str, role: str | None = None) -> User:
    user = User(org_id=org.id, email=email, display_name=email, role=role)
    db.add(user)
    db.flush()
    return user


def make_group(db: Session, org: Organization, name: str) -> Group:
    group = Group(org_id=org.id, name=name)
    db.add(group)
    db.flush()
    return group


def add_membership(db: Session, user: User, group: Group) -> None:
    db.add(GroupMembership(user_id=user.id, group_id=group.id))
    db.flush()


def make_account(db: Session, org: Organization, slug: str, name: str | None = None) -> Account:
    account = Account(org_id=org.id, slug=slug, name=name or slug)
    db.add(account)
    db.flush()
    return account


def make_document(
    db: Session,
    account: Account,
    source: str = "call",
    title: str = "Doc",
    sensitivity: str = "internal",
) -> SourceDocument:
    doc = SourceDocument(
        account_id=account.id,
        source=source,
        title=title,
        sensitivity=sensitivity,
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db.add(doc)
    db.flush()
    return doc


def grant_user_acl(db: Session, document: SourceDocument, user: User) -> None:
    db.add(DocumentUserAcl(document_id=document.id, user_id=user.id))
    db.flush()


def grant_group_acl(db: Session, document: SourceDocument, group: Group) -> None:
    db.add(DocumentGroupAcl(document_id=document.id, group_id=group.id))
    db.flush()


def make_chunk(db: Session, document: SourceDocument, content: str = "content") -> Chunk:
    chunk = Chunk(document_id=document.id, content=content)
    db.add(chunk)
    db.flush()
    return chunk


def make_commitment(
    db: Session,
    account: Account,
    statement: str = "Statement",
    promised_by: str = "Someone",
    authority: str = "sales_unapproved",
    status: str = "at_risk",
) -> Commitment:
    commitment = Commitment(
        account_id=account.id,
        statement=statement,
        promised_by=promised_by,
        promise_date=date(2026, 1, 1),
        delivery_date=None,
        authority=authority,
        status=status,
    )
    db.add(commitment)
    db.flush()
    return commitment


def link_evidence(db: Session, commitment: Commitment, chunk: Chunk, evidence_type: str) -> None:
    db.add(CommitmentEvidence(commitment_id=commitment.id, chunk_id=chunk.id, evidence_type=evidence_type))
    db.flush()
