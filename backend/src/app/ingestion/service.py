"""The ingestion persistence boundary. Parsers never touch the database;
everything here does. `ingest_document` is the single unit of atomicity:
one call, one committed (or rolled back) transaction, one IngestResult.

Security-critical ordering, in every branch below:
  1. Account resolution and enum/ACL-shape validation happen first and
     can only ever REJECT (no write at all).
  2. For an EXISTING document, ACL revocations are computed from the raw
     declared identities (emails/group names) BEFORE any principal
     resolution is attempted, and are always applied — an unresolvable
     *new* principal, or content blocked by a commitment_evidence
     reference, can defer new grants and the content/metadata/chunk
     update, but must never leave an obsolete grant active.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.ingestion.chunking import chunk_content
from app.ingestion.types import IngestResult, NormalizedAcl, NormalizedDocument
from app.models import (
    Account,
    Chunk,
    CommitmentEvidence,
    DocumentGroupAcl,
    DocumentUserAcl,
    Group,
    SourceDocument,
    User,
)

VALID_SOURCES = {"call", "support", "jira", "slack", "contract", "crm"}
VALID_SENSITIVITIES = {"internal", "confidential", "customer_shared"}


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rejected(doc: NormalizedDocument, reason: str) -> IngestResult:
    return IngestResult(
        external_id=doc.external_id, source=doc.source, account_slug=doc.account_slug,
        outcome="rejected", reason=reason,
    )


def ingest_batch(session: Session, org_id: int, documents: list[NormalizedDocument]) -> list[IngestResult]:
    """Rejects same-batch duplicate (source, account_slug, external_id)
    identities before any of them touch the database — no last-write-wins
    within one input file. Cross-run duplicates are the normal upsert
    path in `ingest_document`, not this check.
    """
    seen: set[tuple[str, str, str]] = set()
    results: list[IngestResult] = []
    for doc in documents:
        identity = (doc.source, doc.account_slug, doc.external_id)
        if identity in seen:
            results.append(_rejected(doc, "duplicate external_id within this ingestion run"))
            continue
        seen.add(identity)
        results.append(ingest_document(session, org_id, doc))
    return results


def ingest_document(session: Session, org_id: int, doc: NormalizedDocument) -> IngestResult:
    if doc.source not in VALID_SOURCES:
        return _rejected(doc, f"invalid source '{doc.source}'")
    if doc.sensitivity not in VALID_SENSITIVITIES:
        return _rejected(doc, f"invalid sensitivity '{doc.sensitivity}'")

    account = session.scalar(
        select(Account).where(Account.slug == doc.account_slug, Account.org_id == org_id)
    )
    if account is None:
        return _rejected(doc, f"unknown account '{doc.account_slug}' for this organization")

    if doc.acl is None:
        # We don't know the intended ACL at all — a normal rejection with
        # no update, and critically, no revocations are inferred from it.
        return _rejected(doc, "ACL metadata missing or malformed")

    content_hash = _hash_content(doc.content)
    existing = session.scalar(
        select(SourceDocument).where(
            SourceDocument.account_id == account.id,
            SourceDocument.source == doc.source,
            SourceDocument.external_id == doc.external_id,
        )
    )

    try:
        if existing is None:
            result = _create_document(session, org_id, account.id, doc, content_hash)
        else:
            result = _update_document(session, org_id, existing, doc, content_hash)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def _create_document(
    session: Session, org_id: int, account_id: int, doc: NormalizedDocument, content_hash: str
) -> IngestResult:
    assert doc.acl is not None
    resolved_users, resolved_groups, unresolved = _resolve_principals(session, org_id, doc.acl)
    if unresolved:
        return _rejected(doc, f"unresolved ACL principal(s): {', '.join(sorted(unresolved))}")

    document = SourceDocument(
        account_id=account_id,
        source=doc.source,
        title=doc.title,
        sensitivity=doc.sensitivity,
        occurred_at=doc.occurred_at,
        external_id=doc.external_id,
        content_hash=content_hash,
    )
    session.add(document)
    session.flush()

    for user_id in resolved_users.values():
        session.add(DocumentUserAcl(document_id=document.id, user_id=user_id))
    for group_id in resolved_groups.values():
        session.add(DocumentGroupAcl(document_id=document.id, group_id=group_id))

    _insert_chunks(session, document.id, doc.content)

    return IngestResult(
        external_id=doc.external_id, source=doc.source, account_slug=doc.account_slug,
        outcome="created", document_id=document.id,
    )


def _update_document(
    session: Session, org_id: int, existing: SourceDocument, doc: NormalizedDocument, content_hash: str
) -> IngestResult:
    assert doc.acl is not None
    existing_users, existing_groups = _existing_grants(session, org_id, existing.id)
    desired_users, desired_groups = set(doc.acl.users), set(doc.acl.groups)

    users_to_revoke = existing_users.keys() - desired_users
    groups_to_revoke = existing_groups.keys() - desired_groups
    users_to_add_raw = desired_users - existing_users.keys()
    groups_to_add_raw = desired_groups - existing_groups.keys()

    resolved_new_users, resolved_new_groups, unresolved = _resolve_principals(
        session, org_id, NormalizedAcl(users=sorted(users_to_add_raw), groups=sorted(groups_to_add_raw))
    )

    content_changed = existing.content_hash != content_hash
    referenced = content_changed and _has_referenced_chunks(session, existing.id)
    blocked = referenced or bool(unresolved)

    # Safe revocations always apply, regardless of what blocks the rest —
    # computed from raw declared identities, independent of whether any
    # *new* principal below resolves.
    if users_to_revoke:
        revoke_user_ids = {existing_users[email] for email in users_to_revoke}
        session.execute(
            delete(DocumentUserAcl).where(
                DocumentUserAcl.document_id == existing.id, DocumentUserAcl.user_id.in_(revoke_user_ids)
            )
        )
    if groups_to_revoke:
        revoke_group_ids = {existing_groups[name] for name in groups_to_revoke}
        session.execute(
            delete(DocumentGroupAcl).where(
                DocumentGroupAcl.document_id == existing.id, DocumentGroupAcl.group_id.in_(revoke_group_ids)
            )
        )

    if blocked:
        reasons = []
        if referenced:
            reasons.append("existing chunks are referenced by commitment evidence")
        if unresolved:
            reasons.append(f"one or more declared principals could not be resolved ({', '.join(sorted(unresolved))})")
        reason = (
            f"content update blocked because {' and '.join(reasons)}; "
            "ACL revocations were applied, new grants were withheld"
        )
        return IngestResult(
            external_id=doc.external_id, source=doc.source, account_slug=doc.account_slug,
            outcome="blocked", reason=reason, document_id=existing.id,
        )

    for user_id in resolved_new_users.values():
        session.add(DocumentUserAcl(document_id=existing.id, user_id=user_id))
    for group_id in resolved_new_groups.values():
        session.add(DocumentGroupAcl(document_id=existing.id, group_id=group_id))

    metadata_changed = (
        existing.title != doc.title
        or existing.occurred_at != doc.occurred_at
        or existing.sensitivity != doc.sensitivity
    )
    existing.title = doc.title
    existing.occurred_at = doc.occurred_at
    existing.sensitivity = doc.sensitivity

    if content_changed:
        session.execute(delete(Chunk).where(Chunk.document_id == existing.id))
        existing.content_hash = content_hash
        _insert_chunks(session, existing.id, doc.content)

    acl_changed = bool(users_to_revoke or groups_to_revoke or resolved_new_users or resolved_new_groups)
    outcome = "updated" if (content_changed or metadata_changed or acl_changed) else "unchanged"

    return IngestResult(
        external_id=doc.external_id, source=doc.source, account_slug=doc.account_slug,
        outcome=outcome, document_id=existing.id,
    )


def _insert_chunks(session: Session, document_id: int, content: str) -> None:
    for sequence, text in enumerate(chunk_content(content)):
        session.add(Chunk(document_id=document_id, content=text, sequence=sequence))


def _has_referenced_chunks(session: Session, document_id: int) -> bool:
    subquery = (
        select(CommitmentEvidence.chunk_id)
        .join(Chunk, Chunk.id == CommitmentEvidence.chunk_id)
        .where(Chunk.document_id == document_id)
    )
    return bool(session.scalar(select(exists(subquery))))


def _existing_grants(session: Session, org_id: int, document_id: int) -> tuple[dict[str, int], dict[str, int]]:
    users = dict(
        session.execute(
            select(User.email, User.id)
            .join(DocumentUserAcl, DocumentUserAcl.user_id == User.id)
            .where(DocumentUserAcl.document_id == document_id, User.org_id == org_id)
        ).all()
    )
    groups = dict(
        session.execute(
            select(Group.name, Group.id)
            .join(DocumentGroupAcl, DocumentGroupAcl.group_id == Group.id)
            .where(DocumentGroupAcl.document_id == document_id, Group.org_id == org_id)
        ).all()
    )
    return users, groups


def _resolve_principals(
    session: Session, org_id: int, acl: NormalizedAcl
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    resolved_users = (
        dict(session.execute(select(User.email, User.id).where(User.org_id == org_id, User.email.in_(acl.users))).all())
        if acl.users
        else {}
    )
    resolved_groups = (
        dict(session.execute(select(Group.name, Group.id).where(Group.org_id == org_id, Group.name.in_(acl.groups))).all())
        if acl.groups
        else {}
    )

    unresolved = [u for u in acl.users if u not in resolved_users] + [
        g for g in acl.groups if g not in resolved_groups
    ]
    return resolved_users, resolved_groups, unresolved
