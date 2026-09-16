"""Permission-freshness sequence execution (Milestone 6 design sections 4/7).

Each sequence mutates exactly one permission row between two queries, then
the mutation is always undone before this function returns — regardless of
whether the sequence "passed" — so no sequence can ever leak state into a
later sequence or into any other golden case run in the same process. This
is what makes `test_evaluation_freshness.py`'s "two sequences run in either
order and produce the same outcome" test meaningful: order-independence is
a property of this restore-always guarantee, not an accident of dataset
ordering.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.personas import EvalSeed
from app.evaluation.schema import FreshnessSequence, MutateStep, QueryStep
from app.evaluation.stable_ids import DocumentIdentity, document_ids_for
from app.models import Account, DocumentUserAcl, Group, GroupMembership, SourceDocument, User

# A per-step result is intentionally generic (a dict) — this module knows
# nothing about which evaluation mode (security/retrieval/generation)
# produced it. The runner supplies `run_query_fn`; this module only owns
# mutation/restore sequencing.
QueryRunner = Callable[[QueryStep], dict[str, Any]]


@dataclass
class SequenceStepResult:
    t: str
    persona: str
    result: dict[str, Any]


@dataclass
class SequenceResult:
    sequence_id: str
    steps: list[SequenceStepResult]


def _group_id(db: Session, org_id: int, name: str) -> int:
    group_id = db.scalar(select(Group.id).where(Group.org_id == org_id, Group.name == name))
    assert group_id is not None, f"unknown group {name!r}"
    return group_id


def _apply_mutation(db: Session, seed: EvalSeed, step: MutateStep) -> Callable[[], None]:
    """Applies one mutation and returns a zero-argument callable that
    restores the exact prior state."""
    user = seed.users[step.persona]

    if step.action == "revoke_group_membership":
        group_id = _group_id(db, seed.org.id, step.group)
        db.execute(
            select(GroupMembership).where(GroupMembership.user_id == user.id, GroupMembership.group_id == group_id)
        )
        membership = db.scalar(
            select(GroupMembership).where(GroupMembership.user_id == user.id, GroupMembership.group_id == group_id)
        )
        assert membership is not None, f"{step.persona} is not a member of {step.group!r}"
        db.delete(membership)
        db.commit()

        def restore() -> None:
            db.add(GroupMembership(user_id=user.id, group_id=group_id))
            db.commit()

        return restore

    if step.action == "grant_group_membership":
        group_id = _group_id(db, seed.org.id, step.group)
        db.add(GroupMembership(user_id=user.id, group_id=group_id))
        db.commit()

        def restore() -> None:
            row = db.get(GroupMembership, (user.id, group_id))
            if row is not None:
                db.delete(row)
                db.commit()

        return restore

    if step.action == "revoke_document_acl":
        assert step.account_slug and step.source and step.external_id
        document_id = next(
            iter(
                document_ids_for(
                    db, seed.org.id, step.account_slug,
                    [DocumentIdentity(source=step.source, external_id=step.external_id)],
                )
            ),
            None,
        )
        assert document_id is not None, f"no document for {step.source}/{step.external_id} in {step.account_slug}"
        grant = db.scalar(
            select(DocumentUserAcl).where(
                DocumentUserAcl.document_id == document_id, DocumentUserAcl.user_id == user.id
            )
        )
        assert grant is not None, f"{step.persona} has no direct grant on {step.source}/{step.external_id}"
        db.delete(grant)
        db.commit()

        def restore() -> None:
            db.add(DocumentUserAcl(document_id=document_id, user_id=user.id))
            db.commit()

        return restore

    raise ValueError(f"unknown mutation action {step.action!r}")


def run_sequence(db: Session, seed: EvalSeed, sequence: FreshnessSequence, run_query_fn: QueryRunner) -> SequenceResult:
    step_results: list[SequenceStepResult] = []
    restore_fns: list[Callable[[], None]] = []
    try:
        for step in sequence.steps:
            if isinstance(step, QueryStep):
                result = run_query_fn(step)
                step_results.append(SequenceStepResult(t=step.t, persona=step.persona, result=result))
            else:
                restore_fns.append(_apply_mutation(db, seed, step))
    finally:
        # Always restore, in reverse order, even if a query step raised —
        # a sequence must never leave permission state altered for whatever
        # runs next.
        for restore in reversed(restore_fns):
            restore()

    return SequenceResult(sequence_id=sequence.id, steps=step_results)
