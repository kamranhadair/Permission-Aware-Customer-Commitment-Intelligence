"""Persistent Milestone 7 demo seed.

Deliberately independent of `app.evaluation.*` (personas.py / fixtures_
loader.py): that module is scratch, privileged, benchmark-oriented, and
cleanup-oriented by design (see CLAUDE.md's Milestone 6 section) — a
persistent product demo has the opposite lifecycle. This module reuses
only ordinary production primitives: the real Milestone 3 parsers and
ingestion service, plain ORM models, and the real embedding provider/
backfill. No benchmark cases, golden expectations, forbidden-evidence
metadata, or manual-review fields exist anywhere in this module or in
backend/fixtures/demo/ — there is nothing of that shape to import.

    python -m app.demo.seed [--embedding-provider bge|fake]

Tells one flagship story (the Acme SSO commitment from PRODUCT_SPEC.md)
through two personas whose permitted evidence visibly differs:
  - Maya Chen  <maya@demo.example>  Account Manager  (account-management)
  - Lena Ortiz <lena@demo.example>  Product Manager  (product)
Both can see the sales call and the security ticket; only Lena (product)
can see the internal Slack thread disputing the November date, which is
what surfaces the SSO commitment's conflict for her and not for Maya.

Idempotent and convergent: rerunning checks each expected row by its own
stable natural key (org name, account slug, group name, user email,
ingestion's own (account, source, external_id) upsert identity, commitment
(account, statement)) and creates only what's missing, rather than either
duplicating rows or silently no-op'ing on "org already exists". A run that
hits a real problem (an ambiguous "Demo Org", a rejected/blocked fixture
document, a commitment whose evidence didn't actually get ingested) reports
FAIL lines and a non-zero exit — never a false "success".
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.demo.org import DEMO_ORG_NAME, AmbiguousDemoOrgError, resolve_demo_org
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
from app.retrieval.embed_missing import embed_missing_chunks
from app.retrieval.embeddings import BgeEmbeddingProvider, EmbeddingProvider, FakeEmbeddingProvider

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "demo"

# slug -> display name
EXPECTED_ACCOUNTS: dict[str, str] = {"acme-corp": "Acme Corp"}
EXPECTED_GROUPS = ("account-management", "product")
# email -> (display_name, role/label, group names)
EXPECTED_USERS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "maya@demo.example": ("Maya Chen", "Account Manager", ("account-management",)),
    "lena@demo.example": ("Lena Ortiz", "Product Manager", ("product",)),
}


@dataclass
class SeedReport:
    lines: list[str] = field(default_factory=list)
    failed: bool = False

    def ok(self, msg: str) -> None:
        self.lines.append(f"OK   {msg}")

    def created(self, msg: str) -> None:
        self.lines.append(f"NEW  {msg}")

    def fail(self, msg: str) -> None:
        self.lines.append(f"FAIL {msg}")
        self.failed = True

    def render(self) -> str:
        return "\n".join(self.lines)


def _get_or_create_org(db: Session, report: SeedReport) -> Organization:
    org = resolve_demo_org(db)  # raises AmbiguousDemoOrgError; caller must not swallow it
    if org is not None:
        report.ok(f"organization {DEMO_ORG_NAME!r} already exists (id={org.id})")
        return org
    org = Organization(name=DEMO_ORG_NAME)
    db.add(org)
    db.flush()
    report.created(f"organization {DEMO_ORG_NAME!r} (id={org.id})")
    return org


def _get_or_create_accounts(db: Session, org: Organization, report: SeedReport) -> dict[str, Account]:
    accounts: dict[str, Account] = {}
    for slug, name in EXPECTED_ACCOUNTS.items():
        account = db.scalar(select(Account).where(Account.org_id == org.id, Account.slug == slug))
        if account is None:
            account = Account(org_id=org.id, slug=slug, name=name)
            db.add(account)
            db.flush()
            report.created(f"account '{slug}' (id={account.id})")
        elif account.name != name:
            account.name = name
            report.created(f"account '{slug}' display name updated to {name!r}")
        else:
            report.ok(f"account '{slug}' already exists (id={account.id})")
        accounts[slug] = account
    return accounts


def _get_or_create_groups(db: Session, org: Organization, report: SeedReport) -> dict[str, Group]:
    groups: dict[str, Group] = {}
    for name in EXPECTED_GROUPS:
        group = db.scalar(select(Group).where(Group.org_id == org.id, Group.name == name))
        if group is None:
            group = Group(org_id=org.id, name=name)
            db.add(group)
            db.flush()
            report.created(f"group '{name}' (id={group.id})")
        else:
            report.ok(f"group '{name}' already exists (id={group.id})")
        groups[name] = group
    return groups


def _get_or_create_users(
    db: Session, org: Organization, groups: dict[str, Group], report: SeedReport
) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, (display_name, role, group_names) in EXPECTED_USERS.items():
        user = db.scalar(select(User).where(User.org_id == org.id, User.email == email))
        if user is None:
            user = User(org_id=org.id, email=email, display_name=display_name, role=role)
            db.add(user)
            db.flush()
            report.created(f"user '{email}' (id={user.id})")
        else:
            report.ok(f"user '{email}' already exists (id={user.id})")
        users[email] = user

        for group_name in group_names:
            group = groups[group_name]
            membership = db.scalar(
                select(GroupMembership).where(
                    GroupMembership.user_id == user.id, GroupMembership.group_id == group.id
                )
            )
            if membership is None:
                db.add(GroupMembership(user_id=user.id, group_id=group.id))
                report.created(f"membership '{email}' -> '{group_name}'")
            else:
                report.ok(f"membership '{email}' -> '{group_name}' already exists")
    return users


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _ingest_fixtures(db: Session, org: Organization, report: SeedReport) -> None:
    support_docs, support_errors = support_parser.parse(_load(FIXTURES_DIR / "support" / "tickets.json"))
    call_docs, call_errors = calls_parser.parse(_load(FIXTURES_DIR / "calls" / "calls.json"))
    slack_docs, slack_errors = slack_parser.parse(
        _load(FIXTURES_DIR / "slack" / "channels.json"), _load(FIXTURES_DIR / "slack" / "messages.json")
    )
    for err in support_errors + call_errors + slack_errors:
        report.fail(f"fixture parse error: {err}")
    if report.failed:
        return

    documents = support_docs + call_docs + slack_docs
    results = ingest_batch(db, org.id, documents)
    for result in results:
        if result.outcome in ("rejected", "blocked"):
            report.fail(f"ingestion {result.outcome} for {result.source}/{result.external_id}: {result.reason}")
        else:
            report.ok(f"ingested {result.source}/{result.external_id} -> {result.outcome}")


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


def _get_or_create_commitment(
    db: Session,
    account: Account,
    statement: str,
    *,
    promised_by: str,
    promise_date: date,
    delivery_date: date | None,
    authority: str,
    status: str,
    supporting: list[tuple[str, str]],
    conflicting: list[tuple[str, str]],
    report: SeedReport,
) -> None:
    existing = db.scalar(
        select(Commitment).where(Commitment.account_id == account.id, Commitment.statement == statement)
    )
    if existing is not None:
        report.ok(f"commitment '{statement}' already exists (id={existing.id})")
        return

    supporting_chunks: list[Chunk] = []
    for source, external_id in supporting:
        chunks = _chunks_for(db, account.slug, source, external_id)
        if not chunks:
            report.fail(
                f"commitment '{statement}': no ingested chunks found for supporting evidence {source}/{external_id}"
            )
            return
        supporting_chunks.extend(chunks)

    conflicting_chunks: list[Chunk] = []
    for source, external_id in conflicting:
        chunks = _chunks_for(db, account.slug, source, external_id)
        if not chunks:
            report.fail(
                f"commitment '{statement}': no ingested chunks found for conflicting evidence {source}/{external_id}"
            )
            return
        conflicting_chunks.extend(chunks)

    commitment = Commitment(
        account_id=account.id,
        statement=statement,
        promised_by=promised_by,
        promise_date=promise_date,
        delivery_date=delivery_date,
        authority=authority,
        status=status,
    )
    db.add(commitment)
    db.flush()
    for chunk in supporting_chunks:
        db.add(CommitmentEvidence(commitment_id=commitment.id, chunk_id=chunk.id, evidence_type="supporting"))
    for chunk in conflicting_chunks:
        db.add(CommitmentEvidence(commitment_id=commitment.id, chunk_id=chunk.id, evidence_type="conflicting"))
    report.created(f"commitment '{statement}' (id={commitment.id})")


def _seed_commitments(db: Session, accounts: dict[str, Account], report: SeedReport) -> None:
    acme = accounts["acme-corp"]

    # sales_unapproved, at_risk — supporting evidence both personas can see
    # (the sales call), conflicting evidence only Product can see (the
    # internal Slack thread). This is the flagship conflict the demo exists
    # to show: Maya (account-management) never learns the conflict exists;
    # Lena (product) sees it as an ordinary grounded claim.
    _get_or_create_commitment(
        db,
        acme,
        "Enterprise SSO by November 15",
        promised_by="AE · Account Executive",
        promise_date=date(2026, 8, 12),
        delivery_date=date(2026, 11, 15),
        authority="sales_unapproved",
        status="at_risk",
        supporting=[("call", "DEMO-CALL-1")],
        conflicting=[("slack", "DEMO-PRODUCT-INTERNAL:1723600000.0001")],
        report=report,
    )

    # product_approved, overdue — evidence visible to both personas, no
    # conflict. Demonstrates the non-conflicted case in the same account.
    _get_or_create_commitment(
        db,
        acme,
        "Complete security questionnaire",
        promised_by="Account Manager",
        promise_date=date(2026, 9, 5),
        delivery_date=date(2026, 9, 12),
        authority="product_approved",
        status="overdue",
        supporting=[("support", "DEMO-TICK-1")],
        conflicting=[],
        report=report,
    )


def _embed_chunks(db: Session, provider: EmbeddingProvider, report: SeedReport) -> None:
    total = embed_missing_chunks(db, provider)
    if total:
        report.created(f"embedded {total} chunk(s)")
    else:
        report.ok("no chunks needed embedding")

    remaining = list(db.scalars(select(Chunk.id).where(Chunk.embedding.is_(None))))
    if remaining:
        report.fail(f"{len(remaining)} chunk(s) still unembedded after backfill: {remaining}")


def seed(db: Session, embedding_provider: EmbeddingProvider | None = None) -> SeedReport:
    """Converges the database to the expected persistent demo state and
    returns a report describing exactly what was created vs. already
    present vs. failed. Never returns a report claiming success when
    `report.failed` is true — callers (the CLI, tests) must check that
    flag rather than assume a return means success.

    Raises AmbiguousDemoOrgError before making any write if more than one
    "Demo Org" row already exists — that precondition must never be
    silently worked around.
    """
    report = SeedReport()

    org = _get_or_create_org(db, report)
    db.commit()

    accounts = _get_or_create_accounts(db, org, report)
    groups = _get_or_create_groups(db, org, report)
    _get_or_create_users(db, org, groups, report)
    db.commit()

    _ingest_fixtures(db, org, report)
    if report.failed:
        return report

    _seed_commitments(db, accounts, report)
    if report.failed:
        db.commit()  # keep whatever ingestion already committed; nothing partial about commitments was written
        return report
    db.commit()

    provider = embedding_provider or BgeEmbeddingProvider()
    _embed_chunks(db, provider, report)
    db.commit()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.demo.seed")
    parser.add_argument(
        "--embedding-provider",
        choices=["bge", "fake"],
        default="bge",
        help="'fake' skips loading the real BGE model — useful without the 'embeddings' extra installed.",
    )
    args = parser.parse_args(argv)
    provider: EmbeddingProvider = FakeEmbeddingProvider() if args.embedding_provider == "fake" else BgeEmbeddingProvider()

    session = SessionLocal()
    try:
        report = seed(session, embedding_provider=provider)
    except AmbiguousDemoOrgError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        print("Resolve by removing/renaming the extra organization row(s) before rerunning.", file=sys.stderr)
        return 1
    finally:
        session.close()

    print(report.render())
    if report.failed:
        print("\ndemo seed did NOT converge — see FAIL lines above", file=sys.stderr)
        return 1
    print("\ndemo seed converged successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
