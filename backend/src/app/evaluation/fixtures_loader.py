"""Ingests both the Milestone 3 fixtures (backend/fixtures/{support,calls,slack})
and the Milestone 6 evaluation-only fixtures (backend/fixtures/evaluation/)
into one organization, then hand-seeds the five commitments the golden
dataset's authority cases need.

Evaluation-only fixtures are kept in a separate directory from Milestone 3's
own fixtures deliberately — Milestone 3's fixtures are load-bearing for
`test_ingestion_*.py` (specific counts/content asserted there); nothing in
this module ever touches or extends them.

Every hand-seeded Commitment's authority label is backed by evidence text
that actually supports it (see backend/fixtures/evaluation/{calls,slack}/*)
rather than being a bare DB label with no grounding — that's what makes the
commitment_authority golden cases non-tautological.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.models import Account, Chunk, Commitment, CommitmentEvidence, SourceDocument
from app.retrieval.embeddings import EmbeddingProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
M3_FIXTURES = BACKEND_DIR / "fixtures"
EVAL_FIXTURES = BACKEND_DIR / "fixtures" / "evaluation"


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def ingest_all_fixtures(db: Session, org_id: int) -> None:
    documents = []

    support_docs, _ = support_parser.parse(_load(M3_FIXTURES / "support" / "tickets.json"))
    call_docs, _ = calls_parser.parse(_load(M3_FIXTURES / "calls" / "calls.json"))
    slack_docs, _ = slack_parser.parse(
        _load(M3_FIXTURES / "slack" / "channels.json"), _load(M3_FIXTURES / "slack" / "messages.json")
    )
    documents += support_docs + call_docs + slack_docs

    eval_support_docs, _ = support_parser.parse(_load(EVAL_FIXTURES / "support" / "tickets.json"))
    eval_call_docs, _ = calls_parser.parse(_load(EVAL_FIXTURES / "calls" / "calls.json"))
    eval_slack_docs, _ = slack_parser.parse(
        _load(EVAL_FIXTURES / "slack" / "channels.json"), _load(EVAL_FIXTURES / "slack" / "messages.json")
    )
    documents += eval_support_docs + eval_call_docs + eval_slack_docs

    ingest_batch(db, org_id, documents)


def _chunks_for(db: Session, account_slug: str, source: str, external_id: str) -> list[Chunk]:
    rows = (
        db.execute(
            select(Chunk)
            .join(SourceDocument, SourceDocument.id == Chunk.document_id)
            .join(Account, Account.id == SourceDocument.account_id)
            .where(
                Account.slug == account_slug,
                SourceDocument.source == source,
                SourceDocument.external_id == external_id,
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def seed_commitments(db: Session, accounts: dict[str, Account]) -> dict[str, Commitment]:
    def link(commitment: Commitment, chunks: list[Chunk], evidence_type: str) -> None:
        assert chunks, f"expected chunks for commitment {commitment.statement!r}"
        for chunk in chunks:
            db.add(CommitmentEvidence(commitment_id=commitment.id, chunk_id=chunk.id, evidence_type=evidence_type))

    commitments: dict[str, Commitment] = {}

    # sales_unapproved — Sales told the customer the fix was coming without
    # Product's sign-off; Product's own internal thread explicitly disputes it.
    commitment_a = Commitment(
        account_id=accounts["acme-corp"].id,
        statement="Sales communicated a November SSO fix date to Acme",
        promised_by="AE",
        promise_date=date(2026, 8, 6),
        delivery_date=date(2026, 11, 15),
        authority="sales_unapproved",
        status="at_risk",
    )
    db.add(commitment_a)
    db.flush()
    link(commitment_a, _chunks_for(db, "acme-corp", "call", "CALL-2001"), "supporting")
    link(commitment_a, _chunks_for(db, "acme-corp", "slack", "C-ACME-INTERNAL:1722000000.0001"), "conflicting")
    commitments["sales_unapproved"] = commitment_a

    # product_target — an internal roadmap note, explicitly "unscheduled".
    commitment_b = Commitment(
        account_id=accounts["globex-inc"].id,
        statement="Product is targeting a rate limit increase for Globex, unscheduled",
        promised_by="Product",
        promise_date=date(2026, 8, 7),
        delivery_date=None,
        authority="product_target",
        status="at_risk",
    )
    db.add(commitment_b)
    db.flush()
    link(commitment_b, _chunks_for(db, "globex-inc", "slack", "C-GLOBEX-INTERNAL:1722020000.0001"), "supporting")
    commitments["product_target"] = commitment_b

    # customer_expectation — the CUSTOMER states an expectation; the AE
    # explicitly declines to confirm it. Not a company promise of any kind.
    commitment_c = Commitment(
        account_id=accounts["initech-ltd"].id,
        statement="Initech expects SSO enforcement included in the standard package at no extra fee",
        promised_by="Customer",
        promise_date=date(2026, 6, 1),
        delivery_date=None,
        authority="customer_expectation",
        status="at_risk",
    )
    db.add(commitment_c)
    db.flush()
    link(commitment_c, _chunks_for(db, "initech-ltd", "call", "CALL-3001"), "supporting")
    commitments["customer_expectation"] = commitment_c

    # product_approved — explicit sign-off language ("Approved", "signed off
    # by the Product Lead"), distinct from the unscheduled product_target case.
    commitment_d = Commitment(
        account_id=accounts["initech-ltd"].id,
        statement="Product has approved SSO enforcement for Initech, confirmed for Q4",
        promised_by="Product Lead",
        promise_date=date(2026, 7, 1),
        delivery_date=date(2026, 12, 31),
        authority="product_approved",
        status="on_track",
    )
    db.add(commitment_d)
    db.flush()
    link(commitment_d, _chunks_for(db, "initech-ltd", "slack", "C-INITECH-INTERNAL:1782900000.0000"), "supporting")
    commitments["product_approved"] = commitment_d

    # contractual — an explicit signed-MSA clause, confirmed on the call as
    # "a contractual commitment ... not just a target".
    commitment_e = Commitment(
        account_id=accounts["initech-ltd"].id,
        statement="Initech's signed MSA contractually obligates SSO enforcement by December 31",
        promised_by="AE",
        promise_date=date(2026, 8, 1),
        delivery_date=date(2026, 12, 31),
        authority="contractual",
        status="on_track",
    )
    db.add(commitment_e)
    db.flush()
    link(commitment_e, _chunks_for(db, "initech-ltd", "call", "CALL-3002"), "supporting")
    commitments["contractual"] = commitment_e

    db.commit()
    return commitments


def embed_all_chunks(db: Session, provider: EmbeddingProvider) -> None:
    chunks = list(db.scalars(select(Chunk)))
    if not chunks:
        return
    embeddings = provider.embed_documents([c.content for c in chunks])
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
    db.commit()
