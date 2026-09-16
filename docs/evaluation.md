# Evaluation Plan

## Status as of Milestone 4

The retrieval-only slice of this plan has an initial implementation: `backend/fixtures/retrieval_eval/golden_queries.json` (10 queries) and `python -m app.retrieval.evaluate` (a manual script, not part of `pytest`; requires the optional `embeddings` extra since the paraphrase/semantic cases are meaningless against the deterministic test-only embedding provider). It computes Recall@5, Recall@10, and MRR per category, plus the hard security gate `unauthorized_candidate_count == 0`, against real ingested-and-embedded fixture data across two accounts and three personas (direct-user ACL, group ACL, and cross-persona permission-exclusion cases).

This is a first slice toward, not a replacement for, the 50+ question dataset below — it covers only 5 of the 6 categories at a fraction of the target count, and it stops at retrieval (no generation exists yet to evaluate). **Known coverage gap**: none of the 10 queries empirically demonstrates hybrid fusion being *necessary* — i.e. a real query where neither the lexical channel nor the vector channel alone would surface the target chunk, but the RRF merge does. RRF's combination logic is proven correct at the unit level (`backend/tests/test_retrieval_hybrid.py`, using synthetic ranks), but not yet against the real embedding model on real fixture text. This was identified and deliberately left as a candidate item for the eventual full golden dataset rather than added as an unverified case padded onto the current set.

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
