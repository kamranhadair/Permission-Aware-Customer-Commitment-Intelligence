# Artifact Index

Start here if you are opening the project for the first time.

| Artifact | Purpose |
|---|---|
| `README.md` | Run instructions and project orientation. |
| `PRODUCT_SPEC.md` | Product thesis, WHAT YOU BUILD, THE RULE THAT MATTERS, HOW YOU EVALUATE IT, FDE SIGNAL, and MAKE IT YOUR OWN. |
| `docs/architecture.md` | V1 boundaries and the future permission-first retrieval path. |
| `docs/evaluation.md` | 50+ question golden-dataset structure and separate retrieval/generation/security metrics. |
| `docs/sample-data-models.md` | Compact ACL-aware evidence, commitment, and user contracts. |
| `frontend/` | Runnable Next.js frontend scaffold using typed mock data. |
| `frontend/tests/` | Permission, commitment, dashboard, and answer-scope tests. |
| `future/README.md` | Backend/data-plane work intentionally deferred to avoid over-engineering. |
| `docs/superpowers/specs/` | Approved design snapshot. |
| `docs/superpowers/plans/` | Implementation plan used for this scaffold. |

## Recommended first edits

1. Replace or extend `frontend/src/data/mockData.ts` with your own realistic accounts and evidence.
2. Refine the account and search UX while the domain model is still cheap to change.
3. When ready for backend work, preserve the tested rule in `frontend/src/lib/permissions.ts`: permitted evidence is determined before answer assembly.
4. Add the real API/data layer only when the frontend contracts are stable enough to justify it.
