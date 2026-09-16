"""Validates the golden dataset's evaluator-privileged claims against the
real seeded database, rather than trusting them "by construction."

Two things get checked per single-shot golden case:

1. Every `expected_evidence`/`forbidden_evidence` stable reference
   (`{source, external_id}`) resolves to EXACTLY ONE real document in the
   case's own account — zero means a typo turned into a silent retrieval
   miss instead of a loud dataset error; more than one would make the
   reference itself ambiguous.
2. Every `forbidden_evidence` reference is actually outside the named
   persona's permitted-document set at the (static) baseline seed state —
   if the golden file mislabels a permitted document as forbidden, that's
   a dataset bug, not a security finding, and must fail loudly rather than
   silently passing every "forbidden absent" check for the wrong reason.
3. `expected_evidence` and `forbidden_evidence` never overlap for the same
   case.

`permission_freshness.json` sequences are validated only for (1) and (3)
per query step — the "forbidden must be outside permitted" check does not
apply uniformly there, since a sequence's whole point is that permission
state changes *during* the sequence (a T2 step's forbidden_evidence is
only forbidden *after* the mutation runs, not at the static baseline this
module checks against). That property is instead proven at runtime by the
sequence's own pass/fail outcome (see freshness.py / test_evaluation_freshness.py),
not re-derived here.

This module is evaluator-only, privileged tooling: it reads golden-dataset
fields that must never reach `GenerationContext` or a Gemini request (see
test_evaluation_privilege_isolation.py) and never will, since it only ever
talks to the permission resolver and stable_ids, never generation/*.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.evaluation.personas import EvalSeed
from app.evaluation.schema import FreshnessDataset, GoldenCase, GoldenDataset, QueryStep
from app.evaluation.stable_ids import DocumentIdentity, document_ids_for
from app.permissions.resolver import get_permitted_document_ids, get_user_context


class DatasetValidationError(ValueError):
    """Raised when the golden dataset itself is malformed — never a
    retrieval/generation/permission failure. A caller should treat this as
    a broken evaluation run, not a scored case."""


def _resolve_one(db: Session, org_id: int, account_slug: str, source: str, external_id: str) -> int | None:
    ids = document_ids_for(db, org_id, account_slug, [DocumentIdentity(source=source, external_id=external_id)])
    return next(iter(ids)) if len(ids) == 1 else None


def _validate_case(db: Session, seed: EvalSeed, case: GoldenCase) -> list[str]:
    errors: list[str] = []

    expected_pairs = {(r.source, r.external_id) for r in case.expected_evidence}
    forbidden_pairs = {(r.source, r.external_id) for r in case.forbidden_evidence}
    overlap = expected_pairs & forbidden_pairs
    if overlap:
        errors.append(f"{case.id}: expected_evidence and forbidden_evidence overlap: {sorted(overlap)}")

    if case.account_slug not in seed.accounts:
        errors.append(f"{case.id}: unknown account_slug {case.account_slug!r}")
        return errors  # nothing further is resolvable without a real account

    for ref in case.expected_evidence:
        resolved_count = len(
            document_ids_for(db, seed.org.id, case.account_slug, [DocumentIdentity(ref.source, ref.external_id)])
        )
        if resolved_count != 1:
            errors.append(
                f"{case.id}: expected_evidence {ref.source}/{ref.external_id} resolved to "
                f"{resolved_count} documents in {case.account_slug!r} (expected exactly 1)"
            )

    if case.persona not in seed.users:
        errors.append(f"{case.id}: unknown persona {case.persona!r}")
        return errors

    user_ctx = get_user_context(db, seed.users[case.persona].id)
    permitted = get_permitted_document_ids(db, user_ctx, None)

    for ref in case.forbidden_evidence:
        doc_id = _resolve_one(db, seed.org.id, case.account_slug, ref.source, ref.external_id)
        if doc_id is None:
            errors.append(
                f"{case.id}: forbidden_evidence {ref.source}/{ref.external_id} did not resolve to exactly "
                f"one document in {case.account_slug!r}"
            )
            continue
        if doc_id in permitted:
            errors.append(
                f"{case.id}: forbidden_evidence {ref.source}/{ref.external_id} is actually PERMITTED for "
                f"persona {case.persona!r} at baseline — the dataset mislabels it, this is not a security finding"
            )

    return errors


def validate_golden_dataset(db: Session, seed: EvalSeed, dataset: GoldenDataset) -> list[str]:
    errors: list[str] = []
    for case in dataset.cases:
        errors.extend(_validate_case(db, seed, case))
    return errors


def _validate_query_step(db: Session, seed: EvalSeed, sequence_id: str, step: QueryStep) -> list[str]:
    errors: list[str] = []
    expected_pairs = {(r.source, r.external_id) for r in step.expected_evidence}
    forbidden_pairs = {(r.source, r.external_id) for r in step.forbidden_evidence}
    overlap = expected_pairs & forbidden_pairs
    if overlap:
        errors.append(f"{sequence_id}/{step.t}: expected_evidence and forbidden_evidence overlap: {sorted(overlap)}")

    if step.account_slug not in seed.accounts:
        errors.append(f"{sequence_id}/{step.t}: unknown account_slug {step.account_slug!r}")
        return errors

    for ref in step.expected_evidence + step.forbidden_evidence:
        resolved_count = len(
            document_ids_for(db, seed.org.id, step.account_slug, [DocumentIdentity(ref.source, ref.external_id)])
        )
        if resolved_count != 1:
            errors.append(
                f"{sequence_id}/{step.t}: {ref.source}/{ref.external_id} resolved to {resolved_count} "
                f"documents in {step.account_slug!r} (expected exactly 1)"
            )
    return errors


def validate_freshness_dataset(db: Session, seed: EvalSeed, freshness: FreshnessDataset) -> list[str]:
    errors: list[str] = []
    for sequence in freshness.sequences:
        for step in sequence.steps:
            if isinstance(step, QueryStep):
                errors.extend(_validate_query_step(db, seed, sequence.id, step))
    return errors
