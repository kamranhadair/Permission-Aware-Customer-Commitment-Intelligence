"""Proves `cleanup_eval_orgs` deletes exactly the rows seeded under the
given org ids and nothing else — the load-bearing regression for the
runner's standalone (owns_session) lifecycle cleanup.

Ids are captured as plain ints before cleanup runs and used for every
post-cleanup assertion — never the ORM objects themselves, whose attributes
would otherwise trigger a refresh-on-access against rows cleanup already
deleted (SQLAlchemy's ObjectDeletedError, not a real bug in cleanup.py).
"""

from __future__ import annotations

from sqlalchemy import select

from app.evaluation.cleanup import cleanup_eval_orgs
from app.models import Account, Chunk, Commitment, CommitmentEvidence, Group, GroupMembership, Organization, User
from tests.factories import (
    add_membership,
    grant_group_acl,
    link_evidence,
    make_account,
    make_chunk,
    make_commitment,
    make_document,
    make_group,
    make_org,
    make_user,
)


def _seed_one_org(db, name: str) -> dict[str, int]:
    org = make_org(db, name)
    account = make_account(db, org, f"{name}-acct")
    group = make_group(db, org, "grp")
    user = make_user(db, org, f"{name}@example.com")
    add_membership(db, user, group)
    doc = make_document(db, account)
    grant_group_acl(db, doc, group)
    chunk = make_chunk(db, doc)
    commitment = make_commitment(db, account)
    link_evidence(db, commitment, chunk, "supporting")
    db.commit()
    # Capture plain ints — see module docstring for why.
    return {
        "org_id": org.id, "account_id": account.id, "group_id": group.id, "user_id": user.id,
        "chunk_id": chunk.id, "commitment_id": commitment.id,
    }


def test_cleanup_deletes_everything_under_the_target_org(db):
    ids = _seed_one_org(db, "target")

    cleanup_eval_orgs(db, [ids["org_id"]])

    assert db.get(Organization, ids["org_id"]) is None
    assert db.get(Account, ids["account_id"]) is None
    assert db.get(Group, ids["group_id"]) is None
    assert db.get(User, ids["user_id"]) is None
    assert db.get(Chunk, ids["chunk_id"]) is None
    assert db.get(Commitment, ids["commitment_id"]) is None
    assert db.scalar(select(GroupMembership).where(GroupMembership.user_id == ids["user_id"])) is None
    assert db.scalar(select(CommitmentEvidence).where(CommitmentEvidence.commitment_id == ids["commitment_id"])) is None


def test_cleanup_leaves_a_second_org_untouched(db):
    target_ids = _seed_one_org(db, "target2")
    other_ids = _seed_one_org(db, "other")

    cleanup_eval_orgs(db, [target_ids["org_id"]])

    assert db.get(Organization, target_ids["org_id"]) is None
    # Every row seeded under the OTHER org must still be exactly as it was.
    assert db.get(Organization, other_ids["org_id"]) is not None
    assert db.get(Account, other_ids["account_id"]) is not None
    assert db.get(Group, other_ids["group_id"]) is not None
    assert db.get(User, other_ids["user_id"]) is not None
    assert db.get(Chunk, other_ids["chunk_id"]) is not None
    assert db.get(Commitment, other_ids["commitment_id"]) is not None


def test_cleanup_is_a_noop_for_an_org_with_no_seeded_rows(db):
    org = make_org(db, "empty-org")
    org_id = org.id
    db.commit()

    cleanup_eval_orgs(db, [org_id])  # must not raise

    assert db.get(Organization, org_id) is None


def test_cleanup_with_empty_org_list_does_nothing(db):
    ids = _seed_one_org(db, "untouched-by-empty-call")

    cleanup_eval_orgs(db, [])

    assert db.get(Organization, ids["org_id"]) is not None
