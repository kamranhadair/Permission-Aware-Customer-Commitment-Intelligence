# Evaluation Plan

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
