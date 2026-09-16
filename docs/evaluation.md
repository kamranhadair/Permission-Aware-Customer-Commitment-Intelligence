# Evaluation Plan

## Status as of Milestone 5

The generation-focused slice of this plan now has an initial implementation alongside the retrieval one: `backend/fixtures/generation_eval/golden_questions.json` (12 questions covering lookup, authority distinction, conflicting evidence, temporal update, permission refusal, and insufficient evidence) plus `python -m app.generation.evaluate` (manual, not part of `pytest`; requires the `embeddings` and `generation` extras and a real `GEMINI_API_KEY`).

Automatically-measurable metrics: citation correctness (cited evidence is a subset of the golden case's expected stable `{source, external_id}` set — never the request-local `E1..En` ids, which are not stable across runs), citation completeness (expected evidence is a subset of cited evidence, where required), forbidden-evidence absence, refusal correctness (`status` matches the golden case's expectation), and the two hard security gates (`unauthorized_candidate_count == 0`, `unauthorized_citation_count == 0`).

**Authority and conflict "correctness" deliberately reduce to the same citation-set checks above, not a separate mechanism.** `validate_and_filter_claims` (`backend/src/app/generation/validation.py`) already makes it structurally impossible for a commitment-typed claim to cite a *different* commitment's evidence, or to assert a commitment's authority/status from conflicting-only evidence — so for a golden question scoped to one specific commitment, citation correctness against that commitment's expected evidence automatically catches authority conflation too. No keyword-matching or other free-text semantic check was added for this.

**What is explicitly not automatically scored**: claim-level factual correctness (does the generated sentence actually say the right thing) and the quality of authority/conflict/temporal *wording* are printed for manual review, not scored — the golden schema and the public API contract (final answer text + chunk-level citations, no per-claim structure) do not support a deterministic semantic check without either fragile keyword matching or a second LLM judge call, and Milestone 5 deliberately added neither.

**Real-provider verification actually performed** (2026-09-16, Gemini free tier, model `gemini-2.5-flash`): a direct provider smoke test confirmed structured-output parsing and correct `GenerationFailure` wrapping of a `503` and a `429` provider error. Two full runs of the 12-question slice together produced live answers for 9 of 12 questions before the free tier's 20-requests/day cap was reached; both security gates held at zero across every successful call. One citation-set mismatch (a correct, grounded answer that legitimately cited more evidence than an under-specified golden `expected_evidence` list anticipated) and one status mismatch (the model answered using only permitted evidence rather than abstaining, a documented acceptable alternative — see the golden fixture's own `note` field) were observed; neither is a grounding or security defect. The live prompt-injection case and one live end-to-end `/answer` HTTP round trip were prepared but not run before quota was exhausted — open follow-ups for whoever next runs the eval with a fresh day's quota or a paid tier.

## Status as of Milestone 4 (retrieval only)

The retrieval-only slice of this plan has an initial implementation: `backend/fixtures/retrieval_eval/golden_queries.json` (10 queries) and `python -m app.retrieval.evaluate` (a manual script, not part of `pytest`; requires the optional `embeddings` extra since the paraphrase/semantic cases are meaningless against the deterministic test-only embedding provider). It computes Recall@5, Recall@10, and MRR per category, plus the hard security gate `unauthorized_candidate_count == 0`, against real ingested-and-embedded fixture data across two accounts and three personas (direct-user ACL, group ACL, and cross-persona permission-exclusion cases).

This is a first slice toward, not a replacement for, the 50+ question dataset below — it covers only 5 of the 6 categories at a fraction of the target count, and (as of Milestone 4) stopped at retrieval, before generation existed to evaluate. **Known coverage gap**: none of the 10 queries empirically demonstrates hybrid fusion being *necessary* — i.e. a real query where neither the lexical channel nor the vector channel alone would surface the target chunk, but the RRF merge does. RRF's combination logic is proven correct at the unit level (`backend/tests/test_retrieval_hybrid.py`, using synthetic ranks), but not yet against the real embedding model on real fixture text. This was identified and deliberately left as a candidate item for the eventual full golden dataset rather than added as an unverified case padded onto the current set.

## Golden dataset

Create at least 50 questions across six categories:

| Category | Target |
|---|---:|
| Direct lookup | 8 |
| Cross-document synthesis | 10 |
| Conflicting sources | 10 |
| Stale/temporal | 8 |
| Permission/refusal | 10 |
| Commitment authority | 4 |

Each item should include:

- User/role/group identity.
- Question.
- Expected permitted evidence IDs.
- Forbidden evidence IDs.
- Expected answer facts.
- Expected citations.
- Whether the correct behavior is refusal/insufficient evidence.

## Retrieval evaluation

Evaluate retrieval independently of answer generation.

Recommended metrics:

- Recall@5 and Recall@10 for expected permitted chunks.
- MRR or nDCG for ranking quality.
- Permitted precision.
- Unauthorized retrieval count — hard failure if non-zero.

## Generation evaluation

Milestone 5's 12-question slice (above) implements citation correctness, citation completeness, forbidden-evidence absence, refusal correctness, and the security gates from this list now. Claim/grounded correctness and stale-evidence/authority *wording* quality remain manual-review items, not automated — see the Milestone 5 status note above for why. The full 50+ question dataset and any further automation of these remain deferred to Milestone 6.

Score:

- Grounded correctness.
- Citation correctness.
- Citation completeness.
- Unsupported claims.
- Conflict recognition.
- Stale-evidence handling.
- Authority classification.
- Correct refusals.

## Permission evaluation

Test the same question across multiple users/roles. The permitted evidence set should change before retrieval runs.

Hard invariants:

```text
unauthorized chunks retrieved       = 0
unauthorized chunks reranked        = 0
unauthorized chunks sent to model   = 0
unauthorized facts emitted          = 0
```

## Example golden case

Question: `Has Product committed to delivering SSO by November?`

Evidence:

- Customer call: Sales says “we'll have it in November.”
- Product Slack: PM says “still exploratory; do not communicate November externally.”
- Jira: Q4 target, status under review.

Expected answer: no verified Product commitment; Sales created a customer expectation that conflicts with internal Product evidence.
