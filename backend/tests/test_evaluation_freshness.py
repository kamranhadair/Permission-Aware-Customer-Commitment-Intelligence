"""Proves permission-freshness sequences restore state exactly, so running
multiple sequences in either order produces identical outcomes (Milestone 6
design section 4's explicit requirement) — order-independence is a property
of freshness.py's "always restore" guarantee, not an accident of dataset
ordering.
"""

from __future__ import annotations

from app.evaluation.freshness import run_sequence
from app.evaluation.personas import EvalSeed
from app.evaluation.schema import FreshnessSequence, MutateStep, QueryStep
from app.permissions.resolver import get_permitted_document_ids, get_user_context
from tests.factories import (
    add_membership,
    grant_group_acl,
    grant_user_acl,
    make_account,
    make_chunk,
    make_document,
    make_group,
    make_org,
    make_user,
)


def _build_seed(db) -> tuple[EvalSeed, dict]:
    org = org2 = None
    org = make_org(db, "Test Org")
    org2 = make_org(db, "Test Org Cross")
    account = make_account(db, org, "acct-1")
    group = make_group(db, org, "grp-1")
    user_a = make_user(db, org, "a@example.com")
    user_b = make_user(db, org, "b@example.com")

    doc = make_document(db, account, source="call", title="D1")
    make_chunk(db, doc)
    grant_group_acl(db, doc, group)
    add_membership(db, user_a, group)  # a starts WITH access; b starts WITHOUT

    seed = EvalSeed(
        org=org, cross_org=org2,
        accounts={"acct-1": account},
        users={"a": user_a, "b": user_b},
        groups={"grp-1": group},
    )
    return seed, {"account": account, "group": group, "doc": doc}


def _permitted_snapshot(db, seed: EvalSeed, ctx: dict) -> dict[str, frozenset[int]]:
    return {
        persona: frozenset(get_permitted_document_ids(db, get_user_context(db, user.id), ctx["account"].id))
        for persona, user in seed.users.items()
    }


def _query_step(persona: str) -> QueryStep:
    return QueryStep(
        kind="query", t="T", persona=persona, account_slug="acct-1", query="irrelevant",
        expected_status="answered",
    )


def test_two_sequences_run_in_either_order_produce_same_final_state(db):
    seed, ctx = _build_seed(db)

    seq_revoke_a = FreshnessSequence(
        id="revoke-a",
        steps=[
            _query_step("a"),
            MutateStep(kind="mutate", action="revoke_group_membership", persona="a", group="grp-1"),
            _query_step("a"),
        ],
    )
    seq_grant_b = FreshnessSequence(
        id="grant-b",
        steps=[
            _query_step("b"),
            MutateStep(kind="mutate", action="grant_group_membership", persona="b", group="grp-1"),
            _query_step("b"),
        ],
    )

    def noop_query(step: QueryStep) -> dict:
        return {}

    baseline = _permitted_snapshot(db, seed, ctx)

    run_sequence(db, seed, seq_revoke_a, noop_query)
    after_first = _permitted_snapshot(db, seed, ctx)
    assert after_first == baseline, "sequence must restore state exactly after it finishes"

    run_sequence(db, seed, seq_grant_b, noop_query)
    order_1_final = _permitted_snapshot(db, seed, ctx)
    assert order_1_final == baseline

    # Now run the same two sequences in the OPPOSITE order.
    run_sequence(db, seed, seq_grant_b, noop_query)
    run_sequence(db, seed, seq_revoke_a, noop_query)
    order_2_final = _permitted_snapshot(db, seed, ctx)

    assert order_1_final == order_2_final == baseline


def test_revoke_document_acl_mutation_restores_exact_grant(db):
    org = make_org(db, "Org")
    org2 = make_org(db, "Org2")
    account = make_account(db, org, "acct-2")
    user = make_user(db, org, "c@example.com")
    doc = make_document(db, account, source="support", title="D2")
    make_chunk(db, doc)
    grant_user_acl(db, doc, user)

    seed = EvalSeed(org=org, cross_org=org2, accounts={"acct-2": account}, users={"c": user}, groups={})

    before = get_permitted_document_ids(db, get_user_context(db, user.id), account.id)
    assert doc.id in before

    sequence = FreshnessSequence(
        id="acl-revoke",
        steps=[
            QueryStep(kind="query", t="T1", persona="c", account_slug="acct-2", query="q", expected_status="answered"),
            MutateStep(
                kind="mutate", action="revoke_document_acl", persona="c", account_slug="acct-2",
                source="support", external_id=None,
            ),
        ],
    )
    # external_id must match the ingested document's stable id; set directly since
    # make_document doesn't assign one — patch it onto the doc for this test.
    doc.external_id = "EXT-1"
    doc.content_hash = "hash"
    db.flush()
    sequence.steps[1].external_id = "EXT-1"

    def query_fn(step: QueryStep) -> dict:
        return {}

    run_sequence(db, seed, sequence, query_fn)

    after = get_permitted_document_ids(db, get_user_context(db, user.id), account.id)
    assert doc.id in after, "the grant must be restored after the sequence completes"
