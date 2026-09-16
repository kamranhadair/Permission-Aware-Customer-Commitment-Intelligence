"""Small generation-quality/eval script — manual, not part of `pytest`/CI.
Requires both the `embeddings` and `generation` extras (real BAAI/bge-small
embedding provider and a real Gemini API key via GEMINI_API_KEY).

    python -m app.generation.evaluate

Seeds a dedicated "Generation Eval Org" (never touches real org data),
ingests the three Milestone 3 fixture sources, hand-seeds two Commitment
rows on top of that real ingested evidence (Milestone 3 does not do
commitment extraction, so this mirrors how Milestone 2's own tests seed
commitments), embeds every chunk, then runs each of the 12 golden questions
in fixtures/generation_eval/golden_questions.json against the real
GeminiAnswerGenerator and reports automatically-measurable metrics plus
the two hard security gates. Not idempotent -- run against a scratch
database, not the dev database.

Why authority/conflict "correctness" collapse into plain citation checks:
validate_and_filter_claims (see app/generation/validation.py) already makes
it structurally impossible for a "commitment" claim to cite a DIFFERENT
commitment's evidence, or to assert a commitment's authority/status from
conflicting-only evidence. That means citation correctness against the
single commitment a golden question is about already catches authority
conflation and improper conflict claims -- no separate keyword-matching or
free-text semantic check is added here. Claim-level factual correctness
(does the sentence say the right thing) is NOT automatically measured; it
is printed for manual review, per CLAUDE.md's Milestone 5 scope decision
against crude keyword-matching theater.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.generation.provider import GeminiAnswerGenerator
from app.generation.service import answer
from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.models import (
    Account,
    Chunk,
    Commitment,
    CommitmentEvidence,
    Group,
    GroupMembership,
    Organization,
    SourceDocument,
    User,
)
from app.permissions.resolver import get_permitted_document_ids, get_user_context
from app.retrieval.embeddings import BgeEmbeddingProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES = BACKEND_DIR / "fixtures"
GOLDEN_QUESTIONS = BACKEND_DIR / "fixtures" / "generation_eval" / "golden_questions.json"


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _seed(session) -> tuple[Organization, dict[str, User]]:
    org = Organization(name="Generation Eval Org")
    session.add(org)
    session.flush()

    for slug in ("acme-corp", "globex-inc"):
        session.add(Account(org_id=org.id, slug=slug, name=slug))
    session.flush()

    users = {}
    for name in ("alice", "bob", "carol", "dana"):
        user = User(org_id=org.id, email=f"{name}@vendor.example", display_name=name)
        session.add(user)
        users[name] = user
    session.flush()

    groups = {}
    for name in ("account-management", "product", "exec"):
        group = Group(org_id=org.id, name=name)
        session.add(group)
        groups[name] = group
    session.flush()

    session.add_all(
        [
            GroupMembership(user_id=users["alice"].id, group_id=groups["account-management"].id),
            GroupMembership(user_id=users["bob"].id, group_id=groups["product"].id),
            GroupMembership(user_id=users["carol"].id, group_id=groups["product"].id),
            GroupMembership(user_id=users["carol"].id, group_id=groups["exec"].id),
            # dana can see both the customer-facing call AND the internal
            # product Slack thread -- the "full picture" persona used for
            # the conflict/temporal golden questions.
            GroupMembership(user_id=users["dana"].id, group_id=groups["account-management"].id),
            GroupMembership(user_id=users["dana"].id, group_id=groups["product"].id),
        ]
    )
    session.commit()
    return org, users


def _ingest_fixtures(session, org_id: int) -> None:
    support_docs, _ = support_parser.parse(_load(FIXTURES / "support" / "tickets.json"))
    call_docs, _ = calls_parser.parse(_load(FIXTURES / "calls" / "calls.json"))
    slack_docs, _ = slack_parser.parse(
        _load(FIXTURES / "slack" / "channels.json"), _load(FIXTURES / "slack" / "messages.json")
    )
    ingest_batch(session, org_id, support_docs + call_docs + slack_docs)


def _chunks_for(session, account_slug: str, source: str, external_id: str) -> list[Chunk]:
    rows = session.execute(
        select(Chunk)
        .join(SourceDocument, SourceDocument.id == Chunk.document_id)
        .join(Account, Account.id == SourceDocument.account_id)
        .where(
            Account.slug == account_slug,
            SourceDocument.source == source,
            SourceDocument.external_id == external_id,
        )
    ).scalars().all()
    return list(rows)


def _seed_commitments(session, acme: Account, globex: Account) -> None:
    call_2001 = _chunks_for(session, "acme-corp", "call", "CALL-2001")
    slack_conflict = _chunks_for(session, "acme-corp", "slack", "C-ACME-INTERNAL:1722000000.0001")
    slack_globex = _chunks_for(session, "globex-inc", "slack", "C-GLOBEX-INTERNAL:1722020000.0001")
    assert call_2001 and slack_conflict and slack_globex, "fixture ingestion did not produce the expected chunks"

    commitment_a = Commitment(
        account_id=acme.id,
        statement="Sales communicated a November SSO fix date to Acme",
        promised_by="AE",
        promise_date=date(2026, 8, 6),
        delivery_date=date(2026, 11, 15),
        authority="sales_unapproved",
        status="at_risk",
    )
    session.add(commitment_a)
    session.flush()
    for chunk in call_2001:
        session.add(CommitmentEvidence(commitment_id=commitment_a.id, chunk_id=chunk.id, evidence_type="supporting"))
    for chunk in slack_conflict:
        session.add(CommitmentEvidence(commitment_id=commitment_a.id, chunk_id=chunk.id, evidence_type="conflicting"))

    commitment_b = Commitment(
        account_id=globex.id,
        statement="Product is targeting a rate limit increase for Globex, unscheduled",
        promised_by="Product",
        promise_date=date(2026, 8, 7),
        delivery_date=None,
        authority="product_target",
        status="at_risk",
    )
    session.add(commitment_b)
    session.flush()
    for chunk in slack_globex:
        session.add(CommitmentEvidence(commitment_id=commitment_b.id, chunk_id=chunk.id, evidence_type="supporting"))

    session.commit()


def _embed_all(session, provider: BgeEmbeddingProvider) -> None:
    chunks = list(session.scalars(select(Chunk)))
    if not chunks:
        return
    embeddings = provider.embed_documents([c.content for c in chunks])
    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
    session.commit()


def _stable_identity_for_chunk_ids(session, chunk_ids: set[int]) -> set[tuple[str, str]]:
    if not chunk_ids:
        return set()
    rows = session.execute(
        select(SourceDocument.source, SourceDocument.external_id)
        .join(Chunk, Chunk.document_id == SourceDocument.id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    return {(r.source, r.external_id) for r in rows}


def main() -> int:
    session = SessionLocal()
    embedding_provider = BgeEmbeddingProvider()
    generator = GeminiAnswerGenerator()
    try:
        org, users = _seed(session)
        _ingest_fixtures(session, org.id)
        accounts = {a.slug: a for a in session.scalars(select(Account).where(Account.org_id == org.id))}
        _seed_commitments(session, accounts["acme-corp"], accounts["globex-inc"])
        _embed_all(session, embedding_provider)

        golden = _load(GOLDEN_QUESTIONS)["queries"]
        unauthorized_candidates = 0
        unauthorized_citations = 0
        results = []

        for index, item in enumerate(golden):
            if index > 0:
                # Gemini's free tier caps at 5 requests/minute per model;
                # this is pure operational pacing for the manual eval
                # script, not a retry loop in the generation service itself.
                time.sleep(13)
            persona = users[item["persona"]]
            user_ctx = get_user_context(session, persona.id)
            permitted_docs = get_permitted_document_ids(session, user_ctx)

            try:
                result = answer(session, user_ctx, embedding_provider, generator, item["query"], item["account_slug"])
            except Exception as exc:  # generation_failed is a legitimate, gate-worthy outcome to record
                print(f"[{item['id']}] GENERATION FAILED: {exc}")
                results.append((item, None))
                continue

            assert result is not None, f"{item['id']}: account should be visible to its persona"

            # Security gates, computed the same way retrieval/evaluate.py does.
            for hit_chunk_id in [c.chunk_id for c in result.citations]:
                chunk = session.get(Chunk, hit_chunk_id)
                if chunk is not None and chunk.document_id not in permitted_docs:
                    unauthorized_citations += 1
            for trace_list in (
                result.trace.retrieval_trace.lexical_candidates,
                result.trace.retrieval_trace.vector_candidates,
            ):
                for candidate in trace_list:
                    chunk = session.get(Chunk, candidate.chunk_id)
                    if chunk is not None and chunk.document_id not in permitted_docs:
                        unauthorized_candidates += 1

            cited_ids = {(c.chunk_id) for c in result.citations}
            cited_identity = _stable_identity_for_chunk_ids(session, cited_ids)
            expected_identity = {(e["source"], e["external_id"]) for e in item.get("expected_evidence", [])}
            forbidden_identity = {(e["source"], e["external_id"]) for e in item.get("forbidden_evidence", [])}

            citation_correct = cited_identity <= expected_identity if expected_identity else True
            citation_complete = expected_identity <= cited_identity if expected_identity else True
            forbidden_absent = not (cited_identity & forbidden_identity)
            refusal_correct = result.status == item["expected_status"]

            results.append(
                (
                    item,
                    {
                        "status": result.status,
                        "answer": result.answer,
                        "cited_identity": sorted(cited_identity),
                        "citation_correct": citation_correct,
                        "citation_complete": citation_complete,
                        "forbidden_absent": forbidden_absent,
                        "refusal_correct": refusal_correct,
                        "claims_dropped": result.trace.claims_dropped,
                    },
                )
            )

            print(
                f"[{item['id']}] {item['category']} ({item['persona']}): status={result.status} "
                f"citation_correct={citation_correct} citation_complete={citation_complete} "
                f"forbidden_absent={forbidden_absent} refusal_correct={refusal_correct}"
            )
            print(f"    answer: {result.answer}")

        print()
        print("=== Automatically measurable summary ===")
        scored = [r for _, r in results if r is not None]
        for metric in ("citation_correct", "citation_complete", "forbidden_absent", "refusal_correct"):
            n = len(scored)
            passed = sum(1 for r in scored if r[metric])
            print(f"{metric}: {passed}/{n}")

        print()
        print(f"unauthorized_candidate_count = {unauthorized_candidates}")
        print(f"unauthorized_citation_count = {unauthorized_citations}")
        print()
        print("=== Manual review required (not automatically scored) ===")
        print("claim correctness, authority/conflict wording quality, temporal reasoning quality:")
        for item, r in results:
            if r is not None:
                print(f"  [{item['id']}] expected_status={item['expected_status']} note={item.get('note', '')}")
                print(f"      answer: {r['answer']}")

        assert unauthorized_candidates == 0, "SECURITY GATE FAILED: unauthorized candidate observed"
        assert unauthorized_citations == 0, "SECURITY GATE FAILED: unauthorized citation observed"
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
