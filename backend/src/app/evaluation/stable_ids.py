"""Stable evidence identity: (source, external_id), resolved against the
real ingested rows only at scoring time. Deliberately document-level, not
chunk-level (Milestone 6 design section 5) — a case is satisfied if ANY
permitted chunk belonging to the named document was retrieved/cited, since
Milestone 3's chunker/re-ingestion can change chunk PKs but never a
document's (account, source, external_id) identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Chunk, SourceDocument


@dataclass(frozen=True)
class DocumentIdentity:
    source: str
    external_id: str


def document_ids_for(db: Session, org_id: int, account_slug: str, refs: list[DocumentIdentity]) -> set[int]:
    """Resolve stable (source, external_id) refs to SourceDocument ids,
    scoped to one account within one org. The org_id scope matters because
    this evaluation runner is deliberately not idempotent (each run seeds a
    fresh "Evaluation Org", matching the retired retrieval/evaluate.py and
    generation/evaluate.py scripts' documented behavior) — without it, a
    stale account from a PREVIOUS run sharing the same slug (e.g.
    "acme-corp") could silently resolve instead of the current run's
    account, corrupting stable-id lookups."""
    ids: set[int] = set()
    for ref in refs:
        doc_id = db.scalar(
            select(SourceDocument.id)
            .join(Account, Account.id == SourceDocument.account_id)
            .where(
                Account.org_id == org_id,
                Account.slug == account_slug,
                SourceDocument.source == ref.source,
                SourceDocument.external_id == ref.external_id,
            )
        )
        if doc_id is not None:
            ids.add(doc_id)
    return ids


def chunk_document_map(db: Session, chunk_ids: set[int]) -> dict[int, int]:
    """chunk_id -> document_id, for translating retrieval/citation chunk ids
    up to the document level this module scores against."""
    if not chunk_ids:
        return {}
    rows = db.execute(select(Chunk.id, Chunk.document_id).where(Chunk.id.in_(chunk_ids))).all()
    return {row.id: row.document_id for row in rows}


def document_identities_for_documents(db: Session, document_ids: set[int]) -> set[DocumentIdentity]:
    """The inverse direction: real document ids -> stable identities, used
    by the failure-analysis report (item 17) so it can print "retrieved
    evidence" using the same stable vocabulary as the golden dataset."""
    if not document_ids:
        return set()
    rows = db.execute(
        select(SourceDocument.source, SourceDocument.external_id).where(SourceDocument.id.in_(document_ids))
    ).all()
    return {DocumentIdentity(source=r.source, external_id=r.external_id) for r in rows}
