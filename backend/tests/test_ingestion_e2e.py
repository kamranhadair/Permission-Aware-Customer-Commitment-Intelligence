"""The most important test in Milestone 3: real fixture files, through
the real parsers, through the real ingestion service, checked against the
real (unmodified) Milestone 2 permission resolver — not hand-crafted rows.
"""

import json
from pathlib import Path

from app.ingestion.parsers import calls as calls_parser
from app.ingestion.parsers import slack as slack_parser
from app.ingestion.parsers import support as support_parser
from app.ingestion.service import ingest_batch
from app.permissions.resolver import get_permitted_chunks, get_user_context, get_visible_account
from tests.factories import add_membership, make_account, make_group, make_org, make_user

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES = BACKEND_DIR / "fixtures"


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _seed_org_and_principals(db):
    org = make_org(db, "Vendor Org")
    make_account(db, org, "acme-corp")
    make_account(db, org, "globex-inc")

    alice = make_user(db, org, "alice@vendor.example")
    bob = make_user(db, org, "bob@vendor.example")
    carol = make_user(db, org, "carol@vendor.example")

    account_management = make_group(db, org, "account-management")
    product = make_group(db, org, "product")
    exec_group = make_group(db, org, "exec")

    add_membership(db, alice, account_management)
    add_membership(db, bob, product)
    add_membership(db, carol, product)
    add_membership(db, carol, exec_group)

    other_org = make_org(db, "Other Org")
    make_account(db, other_org, "beta-industries")

    return org, {"alice": alice, "bob": bob, "carol": carol}


def test_fixture_round_trip_permitted_user_sees_chunk_unauthorized_does_not(db):
    org, users = _seed_org_and_principals(db)

    support_docs, support_errors = support_parser.parse(_load(FIXTURES / "support" / "tickets.json"))
    call_docs, call_errors = calls_parser.parse(_load(FIXTURES / "calls" / "calls.json"))
    slack_docs, slack_errors = slack_parser.parse(
        _load(FIXTURES / "slack" / "channels.json"), _load(FIXTURES / "slack" / "messages.json")
    )

    assert len(support_errors) == 1  # TICK-1004 is missing "description" -- a parser-level malformed record
    assert len(call_errors) == 1  # CALL-2003 is missing "transcript"
    assert len(slack_errors) == 1  # the orphaned reply referencing a nonexistent root

    all_docs = support_docs + call_docs + slack_docs
    results = ingest_batch(db, org.id, all_docs)

    outcomes = {(r.source, r.external_id): r.outcome for r in results}
    assert outcomes[("support", "TICK-1001")] == "created"
    assert outcomes[("support", "TICK-1002")] == "created"
    assert outcomes[("support", "TICK-1003")] == "rejected"  # beta-industries is a different org's account
    assert outcomes[("call", "CALL-2001")] == "created"
    assert outcomes[("call", "CALL-2002")] == "created"

    alice_ctx = get_user_context(db, users["alice"].id)
    bob_ctx = get_user_context(db, users["bob"].id)

    acme = get_visible_account(db, alice_ctx, "acme-corp")
    assert acme is not None

    alice_chunks = get_permitted_chunks(db, alice_ctx, acme.id)
    alice_titles = {c.title for c in alice_chunks}
    assert "SSO login intermittently fails for Acme admins" in alice_titles  # direct user ACL
    assert "Acme quarterly business review" in alice_titles  # account-management group ACL
    assert not any(t.startswith("Slack thread in #product-acme-internal") for t in alice_titles)  # not in product/exec

    bob_chunks = get_permitted_chunks(db, bob_ctx, acme.id)
    bob_titles = {c.title for c in bob_chunks}
    assert any(t.startswith("Slack thread in #product-acme-internal") for t in bob_titles)  # bob is in product
    assert "SSO login intermittently fails for Acme admins" not in bob_titles  # alice-only direct grant

    # beta-industries never got ingested (rejected as cross-org) and never becomes visible to anyone in this org.
    assert get_visible_account(db, alice_ctx, "beta-industries") is None


def test_repeated_fixture_ingestion_creates_no_duplicates(db):
    org, users = _seed_org_and_principals(db)
    support_docs, _ = support_parser.parse(_load(FIXTURES / "support" / "tickets.json"))

    first = ingest_batch(db, org.id, support_docs)
    second = ingest_batch(db, org.id, support_docs)

    first_outcomes = [r.outcome for r in first]
    second_outcomes = [r.outcome for r in second]
    assert "created" in first_outcomes
    assert "created" not in second_outcomes
    assert all(o in ("unchanged", "rejected") for o in second_outcomes)
