"""The single canonical evaluation orchestrator (Milestone 6 design section
14). Retires `retrieval/evaluate.py` and `generation/evaluate.py` — this
module absorbs their seeding/ingestion/scoring logic (now shared via
`personas.py`/`fixtures_loader.py`/`metrics.py`) and adds the full golden
dataset, three explicit modes, security gates, and quota-aware resume.

Three modes, deliberately kept apart (Milestone 6 design section 2 — do not
conflate fake-model architecture checks with real-model quality metrics):

- security:   FakeEmbeddingProvider + FakeAnswerGenerator, no network. Runs
              every case AND every permission-freshness sequence. Checks the
              automated structural security gates and permission-exclusion
              correctness. Never reports Recall/MRR — a fake embedding
              provider is semantically meaningless, and reporting retrieval-
              quality numbers computed from it as "quality" would be a lie.
- retrieval:  BgeEmbeddingProvider, no generator call at all (no Gemini
              spend). Full-dataset real Recall@5/10/MRR plus the retrieval-
              scoped security gates.
- generation: BgeEmbeddingProvider + GeminiAnswerGenerator. Real answer
              quality, quota-budgeted via --limit/--start-at/--case-id/
              --resume, persisting enough non-sensitive per-case output
              (backend/.eval-output/, gitignored) that a quota-interrupted
              run can be resumed without re-spending completed calls.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.evaluation import personas as personas_module
from app.evaluation.cleanup import cleanup_eval_orgs
from app.evaluation.dataset_validation import validate_freshness_dataset, validate_golden_dataset
from app.evaluation.fixtures_loader import embed_all_chunks, ingest_all_fixtures, seed_commitments
from app.evaluation.freshness import run_sequence
from app.evaluation.metrics import GenerationScore, mrr, recall_at_k, score_generation
from app.evaluation.schema import FreshnessDataset, GoldenCase, GoldenDataset, QueryStep
from app.evaluation.security_gates import SecurityGateReport, check_generation_gates, check_retrieval_gates, merge_reports
from app.evaluation.stable_ids import DocumentIdentity, document_ids_for
from app.generation.context import build_context
from app.generation.errors import GenerationFailure
from app.generation.provider import AnswerGenerator, FakeAnswerGenerator, GeminiAnswerGenerator
from app.generation.validation import render_answer, validate_and_filter_claims
from app.permissions.resolver import UserContext, get_user_context, get_visible_account, get_visible_commitments
from app.retrieval.embeddings import BgeEmbeddingProvider, EmbeddingProvider, FakeEmbeddingProvider
from app.retrieval.service import retrieve

# Terminal, usable outcomes — a case in one of these states actually
# completed and (except account_not_visible, which needs no model call at
# all) consumed a real provider call. "generation_failure" is deliberately
# excluded: it covers both a provider/network/quota error (the request
# never completed) and a schema-valid response where every claim failed
# grounding validation — neither is a result `--resume` should treat as
# done, since re-running is exactly how a quota-blocked case gets another
# chance without the operator manually tracking which ids are missing.
COMPLETED_STATUSES = {"answered", "insufficient_evidence", "account_not_visible"}


def _resumable_completed_results(persisted_case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """`--resume`'s filter: only a persisted record whose `status_actual` is
    in `COMPLETED_STATUSES` counts as done and gets skipped on the next run.
    A record whose provider call never completed, or whose response was
    schema-valid but fully ungrounded (`generation_failure` either way), is
    excluded here — so it lands back in the "cases still to run" list and
    is retried, rather than becoming a permanent gap `--resume` can never
    fill in. A case that *did* complete and is merely waiting on manual
    review keeps its persisted claims/citations and is never re-sent to the
    provider."""
    return {
        r["case_id"]: r for r in persisted_case_results if r.get("status_actual") in COMPLETED_STATUSES
    }


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
FIXTURES_DIR = BACKEND_DIR / "fixtures" / "evaluation"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / ".eval-output"

Mode = Literal["security", "retrieval", "generation"]

# Cases whose forbidden-evidence stakes are high enough to require a human
# verdict before the two manual security gates can be claimed at zero
# (Milestone 6 design section 3). Selected, not exhaustive: every
# conflicting_evidence case with a forbidden side, and every prompt_injection
# case, since those are exactly the shapes where a model could leak
# something true without ever citing the forbidden id.
MANUAL_REVIEW_CATEGORIES = {"conflicting_evidence", "prompt_injection"}
RESERVED_AUTHORITY_WORDS = (
    "customer_expectation", "sales_unapproved", "product_target", "product_approved", "contractual",
)


def _load_dataset() -> GoldenDataset:
    with (FIXTURES_DIR / "golden_dataset.json").open() as f:
        raw = json.load(f)
    return GoldenDataset.model_validate(raw)


def _load_freshness() -> FreshnessDataset:
    with (FIXTURES_DIR / "permission_freshness.json").open() as f:
        raw = json.load(f)
    return FreshnessDataset.model_validate(raw)


@dataclass
class CaseResult:
    case_id: str
    category: str
    persona: str
    account_slug: str
    mode: Mode
    status_actual: str
    status_ok: bool
    security: dict[str, int]
    security_violation_count: int
    recall_5: float | None = None
    recall_10: float | None = None
    mrr: float | None = None
    generation: dict[str, Any] | None = None
    manual_review: dict[str, str] | None = None
    note_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ManualReviewStatus = Literal["not_required", "pending", "passed", "failed"]
OverallSecurityStatus = Literal["passed", "pending_review", "failed"]


@dataclass
class RunReport:
    mode: Mode
    timestamp: str
    case_results: list[CaseResult]
    freshness_results: list[dict[str, Any]]
    # Mechanically provable from ids alone: ordinary-case structural gates
    # (lexical/vector/hybrid/context/citation) AND permission-freshness
    # sequence violations AND cross-org (account_not_visible) checks. A
    # failing freshness sequence fails this on its own — it is not enough
    # for every flat case to be clean.
    automated_security_all_clear: bool
    # Semantic gates (unauthorized_facts_emitted, hidden_conflict_leakage)
    # that cannot be proven from citation ids alone — see security_gates.py's
    # module docstring. "not_required" means no case in this run was
    # designated for manual review (always true in security/retrieval mode,
    # which must never pretend to prove a semantic model-output property no
    # model was actually asked to produce).
    manual_security_review_status: ManualReviewStatus
    # "passed" only when automated_security_all_clear is True AND
    # manual_security_review_status is "not_required" or "passed".
    # "pending_review" when automated is clean but a manual gate is still
    # pending. "failed" whenever either half fails — never averaged.
    overall_security_status: OverallSecurityStatus


def _stable_refs_to_doc_ids(db: Session, org_id: int, account_slug: str, refs) -> set[int]:
    return document_ids_for(
        db, org_id, account_slug, [DocumentIdentity(source=r.source, external_id=r.external_id) for r in refs]
    )


def _run_retrieval_step(
    db: Session,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    query: str,
    account_slug: str,
):
    """Returns (result_or_None, permitted_document_ids). `permitted_document_ids`
    is always computed (even when the account itself is invisible) so gate
    checks have a consistent set to compare against."""
    from app.permissions.resolver import get_permitted_document_ids

    permitted = get_permitted_document_ids(db, user_ctx, None)
    result = retrieve(db, user_ctx, embedding_provider, query, account_slug=account_slug)
    return result, permitted


def _score_retrieval_case(
    db: Session,
    seed: personas_module.EvalSeed,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    case: GoldenCase,
    mode: Mode,
    compute_recall: bool,
) -> CaseResult:
    result, permitted_all = _run_retrieval_step(db, user_ctx, embedding_provider, case.query, case.account_slug)
    note_flags: list[str] = []

    if result is None:
        status_actual = "account_not_visible"
        gate_report = SecurityGateReport()
        recall5 = recall10 = mrr_score = None
    else:
        # Retrieval alone cannot distinguish "answered" from
        # "insufficient_evidence" — retrieve() has no relevance threshold,
        # it always ranks whatever permitted content exists in the account,
        # even when none of it is actually relevant to the query. That
        # judgment only exists at the generation layer (a real model
        # deciding the retrieved context doesn't answer the question, or
        # the zero-context short-circuit in generation/service.py). Marking
        # every non-empty retrieval result "answered" would misreport every
        # permission_refusal/insufficient_evidence case as a status failure
        # in security/retrieval mode, when the mode simply cannot test that
        # distinction — see docs/evaluation.md.
        status_actual = "retrieved"
        note_flags.append("answered/insufficient_evidence distinction not evaluable outside generation mode")
        gate_report = check_retrieval_gates(db, permitted_all, result.trace)
        # No separate forbidden-evidence check is needed here: every golden
        # case's forbidden_evidence names a document that is, by
        # construction, outside this persona's permitted set — so it is
        # already covered by the general "unauthorized candidate" gates
        # above. A document being genuinely permitted but merely excluded
        # from ranking is not a security question at all.

        if compute_recall and case.expected_evidence:
            # Recall@k is only meaningful when there is a real expected
            # document to find. For expected_evidence=[] cases (permission-
            # exclusion / no-evidence-exists), retrieve() has no relevance
            # threshold and always ranks whatever permitted content exists
            # in the account — so recall_at_k's "1.0 iff nothing returned"
            # convention would score 0.0 by construction, every time,
            # regardless of retrieval quality. Reporting that into a
            # category average would misrepresent a metric artifact as a
            # quality finding, so those cases are excluded here (recall
            # stays None) rather than silently dragging averages down —
            # see docs/evaluation.md.
            expected_doc_ids = _stable_refs_to_doc_ids(db, seed.org.id, case.account_slug, case.expected_evidence)
            ranked_chunk_ids = [h.chunk_id for h in result.hits]
            chunk_to_doc = {h.chunk_id: h.document_id for h in result.hits}
            recall5 = recall_at_k(expected_doc_ids, ranked_chunk_ids, chunk_to_doc, 5)
            recall10 = recall_at_k(expected_doc_ids, ranked_chunk_ids, chunk_to_doc, 10)
            mrr_score = mrr(expected_doc_ids, ranked_chunk_ids, chunk_to_doc)
        else:
            recall5 = recall10 = mrr_score = None

    status_ok = _non_generation_status_ok(case.expected_status, case.statuses_ok(), status_actual)

    return CaseResult(
        case_id=case.id, category=case.category, persona=case.persona, account_slug=case.account_slug, mode=mode,
        status_actual=status_actual, status_ok=status_ok,
        security=gate_report.summary(), security_violation_count=len(gate_report.violations),
        recall_5=recall5, recall_10=recall10, mrr=mrr_score, note_flags=note_flags,
    )


def _non_generation_status_ok(expected_status: str, acceptable_statuses: set[str], status_actual: str) -> bool:
    """security/retrieval modes can only ever observe two outcomes:
    'account_not_visible' (retrieve() returned None) or 'retrieved' (it
    didn't). Only an 'account_not_visible' expectation is meaningfully
    checkable here; an 'answered'/'insufficient_evidence' expectation is
    reported as satisfied (not a failure) because this mode structurally
    cannot evaluate it — see the comment in `_score_retrieval_case`."""
    if "account_not_visible" in acceptable_statuses or expected_status == "account_not_visible":
        return status_actual == "account_not_visible"
    return True


def _authority_for_expected_evidence(db: Session, user_ctx: UserContext, account_id: int, expected_doc_ids: set[int]) -> str | None:
    if not expected_doc_ids:
        return None
    for commitment in get_visible_commitments(db, user_ctx, account_id):
        supporting_doc_ids = {c.document_id for c in commitment.supporting}
        if expected_doc_ids & supporting_doc_ids:
            return commitment.authority
    return None


def _run_generation_case_with_visibility(
    db: Session,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    generator: AnswerGenerator,
    query: str,
    account_slug: str,
):
    """Mirrors `generation/service.py:answer()`'s orchestration exactly
    (same public building blocks, same branch order) but additionally
    returns the raw `GenerationContext` and post-validation `Claim` list —
    visibility the product API deliberately does not expose (its trace is
    safe-by-construction and only carries citation_id strings/counts, never
    chunk/document ids for context). This is legitimate, privileged
    evaluator-only visibility (Milestone 6 design section 17), not a
    modification to the product contract; it never influences what the
    generator itself receives.
    """
    account = get_visible_account(db, user_ctx, account_slug)
    if account is None:
        return None, None, None, None, "account_not_visible"

    retrieval_result = retrieve(db, user_ctx, embedding_provider, query, account_slug=account_slug, limit=8)
    assert retrieval_result is not None
    commitments = get_visible_commitments(db, user_ctx, account.id)
    context = build_context(retrieval_result.hits, commitments)

    if not context.evidence and not context.commitments:
        return [], context, [], retrieval_result, "insufficient_evidence"

    try:
        generated = generator.generate(query, context)
    except GenerationFailure:
        return None, context, None, retrieval_result, "generation_failure"

    if generated.status == "insufficient_evidence":
        return generated.claims, context, [], retrieval_result, "insufficient_evidence"

    valid_claims, summary = validate_and_filter_claims(generated.claims, context)
    if not valid_claims:
        return generated.claims, context, [], retrieval_result, "generation_failure"

    return generated.claims, context, valid_claims, retrieval_result, "answered"


def _score_generation_case(
    db: Session,
    seed: personas_module.EvalSeed,
    user_ctx: UserContext,
    embedding_provider: EmbeddingProvider,
    generator: AnswerGenerator,
    case: GoldenCase,
    mode: Mode,
) -> CaseResult:
    from app.permissions.resolver import get_permitted_document_ids

    permitted_all = get_permitted_document_ids(db, user_ctx, None)
    _raw_claims, context, valid_claims, retrieval_result, status_actual = _run_generation_case_with_visibility(
        db, user_ctx, embedding_provider, generator, case.query, case.account_slug
    )

    gate_reports = []
    note_flags: list[str] = []
    manual_review: dict[str, str] | None = None
    generation_payload: dict[str, Any] | None = None

    if retrieval_result is not None:
        gate_reports.append(check_retrieval_gates(db, permitted_all, retrieval_result.trace))

    account = seed.accounts.get(case.account_slug)

    if context is not None:
        context_doc_ids = [c.document_id for c in context.evidence]
        cited_doc_ids: list[int] = []
        if valid_claims:
            by_citation = {c.citation_id: c for c in context.evidence}
            seen: set[int] = set()
            for claim in valid_claims:
                for cid in claim.citation_ids:
                    chunk = by_citation.get(cid)
                    if chunk is not None and chunk.document_id not in seen:
                        seen.add(chunk.document_id)
                        cited_doc_ids.append(chunk.document_id)
        gate_reports.append(check_generation_gates(permitted_all, context_doc_ids, cited_doc_ids))

        expected_doc_ids = _stable_refs_to_doc_ids(db, seed.org.id, case.account_slug, case.expected_evidence)
        forbidden_doc_ids = _stable_refs_to_doc_ids(db, seed.org.id, case.account_slug, case.forbidden_evidence)
        expected_temporal_doc_id = None
        if case.expected_temporal_precedence is not None:
            ids = _stable_refs_to_doc_ids(db, seed.org.id, case.account_slug, [case.expected_temporal_precedence])
            expected_temporal_doc_id = next(iter(ids), None)

        actual_authority = None
        if case.expected_authority is not None and account is not None:
            actual_authority = _authority_for_expected_evidence(db, user_ctx, account.id, expected_doc_ids)

        score: GenerationScore = score_generation(
            actual_status=status_actual,
            acceptable_statuses=case.statuses_ok(),
            cited_doc_ids=set(cited_doc_ids),
            expected_doc_ids=expected_doc_ids,
            forbidden_doc_ids=forbidden_doc_ids,
            expected_temporal_doc_id=expected_temporal_doc_id,
            expected_authority=case.expected_authority,
            actual_authority_for_expected_evidence=actual_authority,
        )

        answer_text = render_answer(valid_claims) if valid_claims else (
            "No permitted evidence available to this user supports a grounded answer to this question."
            if status_actual == "insufficient_evidence" else None
        )

        if "no_reserved_authority_word_without_commitment" in case.structural_checks:
            if context.commitments:
                note_flags.append("STRUCTURAL CHECK FAILED: commitments present where none were expected")
            elif answer_text and any(word in answer_text for word in RESERVED_AUTHORITY_WORDS):
                note_flags.append("reserved authority word present in answer text — flagged for manual review")

        generation_payload = {
            "status": status_actual,
            "answer": answer_text,
            "claims": [
                {"claim_type": c.claim_type, "citation_ids": c.citation_ids} for c in (valid_claims or [])
            ],
            "cited_stable_ids": sorted(
                (r.source, r.external_id)
                for r in _resolve_doc_ids_to_refs(db, cited_doc_ids)
            ),
            "score": asdict(score),
        }

        if case.category in MANUAL_REVIEW_CATEGORIES:
            manual_review = {"unauthorized_fact_emitted": "pending_review", "hidden_conflict_leakage": "pending_review"}

    merged_gates = merge_reports(*gate_reports) if gate_reports else SecurityGateReport()
    status_ok = status_actual in case.statuses_ok()

    return CaseResult(
        case_id=case.id, category=case.category, persona=case.persona, account_slug=case.account_slug, mode=mode,
        status_actual=status_actual, status_ok=status_ok,
        security=merged_gates.summary(), security_violation_count=len(merged_gates.violations),
        generation=generation_payload, manual_review=manual_review, note_flags=note_flags,
    )


def _resolve_doc_ids_to_refs(db: Session, doc_ids: list[int]):
    from app.evaluation.stable_ids import document_identities_for_documents

    return document_identities_for_documents(db, set(doc_ids))


def _run_freshness_sequences(
    db: Session, seed: personas_module.EvalSeed, embedding_provider: EmbeddingProvider
) -> list[dict[str, Any]]:
    freshness = _load_freshness()
    results = []
    for sequence in freshness.sequences:

        def run_query(step: QueryStep) -> dict[str, Any]:
            user_ctx = get_user_context(db, seed.users[step.persona].id)
            from app.permissions.resolver import get_permitted_document_ids

            permitted = get_permitted_document_ids(db, user_ctx, None)
            result = retrieve(db, user_ctx, embedding_provider, step.query, account_slug=step.account_slug)
            if result is None:
                status_actual = "account_not_visible"
                gates = SecurityGateReport()
                hit_doc_ids: set[int] = set()
            else:
                # See _score_retrieval_case's comment: retrieval alone
                # cannot distinguish answered/insufficient_evidence.
                status_actual = "retrieved"
                gates = check_retrieval_gates(db, permitted, result.trace)
                hit_doc_ids = {h.document_id for h in result.hits}

            forbidden_doc_ids = _stable_refs_to_doc_ids(db, seed.org.id, step.account_slug, step.forbidden_evidence)
            forbidden_absent = not (hit_doc_ids & forbidden_doc_ids)
            return {
                "status_actual": status_actual,
                "status_ok": _non_generation_status_ok(step.expected_status, step.statuses_ok(), status_actual),
                "forbidden_absent": forbidden_absent,
                "security_violations": len(gates.violations),
            }

        seq_result = run_sequence(db, seed, sequence, run_query)
        results.append(
            {
                "sequence_id": seq_result.sequence_id,
                "steps": [
                    {"t": s.t, "persona": s.persona, **s.result} for s in seq_result.steps
                ],
            }
        )
    return results


def _compute_security_status(
    all_case_dicts: list[dict[str, Any]], freshness_results: list[dict[str, Any]]
) -> tuple[bool, ManualReviewStatus, OverallSecurityStatus]:
    """See RunReport's field docstrings for the exact semantics. Freshness
    sequence violations count toward `automated_security_all_clear` — a
    single failing sequence step (a security violation OR an unexpectedly-
    present forbidden document) fails the whole automated check, it is not
    enough for every flat case to independently be clean. Takes plain dicts
    (matching both `CaseResult.to_dict()` and a persisted-JSON record's
    shape) so a resumed run's on-disk history and this run's fresh results
    are scored identically."""
    automated_clear = all(d.get("security_violation_count", 0) == 0 for d in all_case_dicts)
    for sequence in freshness_results:
        for step in sequence["steps"]:
            if step["security_violations"] != 0 or not step["forbidden_absent"]:
                automated_clear = False

    manual_gate_values: list[str] = []
    for d in all_case_dicts:
        manual_review = d.get("manual_review")
        if not manual_review:
            continue
        for gate, value in manual_review.items():
            if gate == "notes":
                continue
            manual_gate_values.append(value)

    if not manual_gate_values:
        manual_status: ManualReviewStatus = "not_required"
    elif any(v == "fail" for v in manual_gate_values):
        manual_status = "failed"
    elif any(v == "pending_review" for v in manual_gate_values):
        manual_status = "pending"
    else:
        manual_status = "passed"

    if not automated_clear or manual_status == "failed":
        overall: OverallSecurityStatus = "failed"
    elif manual_status == "pending":
        overall = "pending_review"
    else:
        overall = "passed"

    return automated_clear, manual_status, overall


def run(
    mode: Mode,
    limit: int | None = None,
    start_at: str | None = None,
    case_id: str | None = None,
    resume: bool = False,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    db: Session | None = None,
) -> RunReport:
    """`db`: an injectable session, defaulting to a fresh `SessionLocal()`
    (matching the retired evaluate.py scripts' standalone/scratch-DB usage
    for real manual runs). Tests pass in the `db` pytest fixture's
    SAVEPOINT-backed session instead, so the seeded "Evaluation Org" never
    leaves committed rows behind in TEST_DATABASE_URL — see
    test_evaluation_runner_fake_mode.py."""
    dataset = _load_dataset()
    cases = dataset.cases

    if case_id is not None:
        cases = [c for c in cases if c.id == case_id]
    elif start_at is not None:
        ids = [c.id for c in cases]
        if start_at in ids:
            cases = cases[ids.index(start_at):]
    if limit is not None:
        cases = cases[:limit]

    previous_results: dict[str, dict] = {}
    output_path = output_dir / f"{mode}-latest.json"
    if resume and output_path.exists():
        with output_path.open() as f:
            previous = json.load(f)
        previous_results = _resumable_completed_results(previous.get("case_results", []))
        cases = [c for c in cases if c.id not in previous_results]

    owns_session = db is None
    session = db if db is not None else SessionLocal()
    seed: personas_module.EvalSeed | None = None
    case_results: list[CaseResult] = []
    freshness_results: list[dict[str, Any]] = []
    try:
        seed = personas_module.seed(session)
        ingest_all_fixtures(session, seed.org.id)
        seed_commitments(session, seed.accounts)

        # Validate the golden dataset's own privileged claims against the
        # real seeded database before trusting any of them "by
        # construction" — see dataset_validation.py. Always validates the
        # full dataset/freshness files, not just the cases this invocation
        # happens to be running, since this is cheap (no embeddings/Gemini)
        # and a malformed case should fail loudly the first time anyone
        # notices, not only on the day someone happens to run it.
        errors = validate_golden_dataset(session, seed, _load_dataset())
        errors += validate_freshness_dataset(session, seed, _load_freshness())
        if errors:
            raise ValueError("Golden dataset validation failed:\n" + "\n".join(errors))

        if mode == "security":
            embedding_provider: EmbeddingProvider = FakeEmbeddingProvider()
            generator: AnswerGenerator = FakeAnswerGenerator()
        else:
            embedding_provider = BgeEmbeddingProvider()
            generator = GeminiAnswerGenerator() if mode == "generation" else FakeAnswerGenerator()

        embed_all_chunks(session, embedding_provider)

        for case in cases:
            user_ctx = get_user_context(session, seed.users[case.persona].id)
            if mode in ("security", "retrieval"):
                result = _score_retrieval_case(
                    session, seed, user_ctx, embedding_provider, case, mode, compute_recall=(mode == "retrieval")
                )
            else:
                result = _score_generation_case(session, seed, user_ctx, embedding_provider, generator, case, mode)
            case_results.append(result)

            if mode == "generation":
                _persist_progress(output_path, mode, case_results, previous_results)

        if mode == "security":
            freshness_results = _run_freshness_sequences(session, seed, embedding_provider)
    finally:
        if owns_session:
            try:
                # Clear any failed-statement state first — safe even on a
                # clean run, since every write up to this point was already
                # committed by personas.seed()/ingest_all_fixtures()/etc.,
                # so this can only discard an incidental empty transaction,
                # never real seeded data.
                session.rollback()
                if seed is not None:
                    cleanup_eval_orgs(session, [seed.org.id, seed.cross_org.id])
            except Exception as cleanup_exc:  # noqa: BLE001 — must never mask the original error
                org_desc = f"org {seed.org.id}" if seed is not None else "a partially-seeded org"
                print(
                    f"WARNING: evaluation cleanup failed for {org_desc} "
                    f"(rows may remain in the database): {cleanup_exc}",
                    file=sys.stderr,
                )
            session.close()

    all_case_dicts = list(previous_results.values()) + [r.to_dict() for r in case_results]
    automated_clear, manual_status, overall_status = _compute_security_status(all_case_dicts, freshness_results)

    report = RunReport(
        mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        case_results=case_results,
        freshness_results=freshness_results,
        automated_security_all_clear=automated_clear,
        manual_security_review_status=manual_status,
        overall_security_status=overall_status,
    )

    if mode == "generation":
        _persist_progress(output_path, mode, case_results, previous_results, final=True, freshness=freshness_results)

    return report


def _persist_progress(
    output_path: Path,
    mode: Mode,
    case_results: list[CaseResult],
    previous_results: dict[str, dict],
    final: bool = False,
    freshness: list[dict[str, Any]] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined = list(previous_results.values()) + [r.to_dict() for r in case_results]
    payload = {
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final": final,
        "case_results": combined,
        "freshness_results": freshness or [],
    }
    with output_path.open("w") as f:
        json.dump(payload, f, indent=2, default=str)


def mark_reviewed(output_dir: Path, case_id: str, gate: str, verdict: str, note: str | None = None) -> None:
    """Records a human verdict for one manual-review security gate on an
    already-persisted generation-mode result, without spending any more
    quota. `verdict` is 'pass' or 'fail'."""
    output_path = output_dir / "generation-latest.json"
    with output_path.open() as f:
        payload = json.load(f)
    for record in payload["case_results"]:
        if record["case_id"] == case_id:
            if record.get("manual_review") is None:
                raise ValueError(f"case {case_id} has no manual_review fields to update")
            record["manual_review"][gate] = verdict
            if note:
                record["manual_review"].setdefault("notes", {})[gate] = note
            break
    else:
        raise ValueError(f"case {case_id} not found in {output_path}")
    with output_path.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
