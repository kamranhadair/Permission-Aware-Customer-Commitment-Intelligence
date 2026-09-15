# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

**Permission-Aware Customer Commitment Intelligence.** Core question the product answers: *what did we promise this customer, and was that promise actually approved?*

This is deliberately **not** a generic enterprise PDF/RAG chatbot. The differentiating workflow is customer-promise intelligence (accounts, commitments, authority, evidence, conflicts) — conversational search is a supporting interface, not the whole product. See `PRODUCT_SPEC.md` for the full thesis and `ARTIFACT_INDEX.md` for a map of every doc in the repo.

## Non-negotiable security invariant

> **Unauthorized evidence must never influence retrieval candidates, reranking, generation context, citations, answers, or traces.**

Filtering an answer after it's produced is too late — the invariant applies to every stage, including audit/trace output (a trace must not become a second place where confidential text leaks).

In the current frontend (mock data, no real retrieval/reranking/LLM yet), this is implemented by filtering evidence through `frontend/src/lib/permissions.ts` **before** any answer or conflict is constructed. See "Current architecture" below for exactly where this happens.

## Current verified state (Milestone 1 — complete)

The frontend scaffold has been verified end-to-end and needed no code changes:

- `npm install` succeeds (0 vulnerabilities)
- `npm run typecheck` passes
- `npm test` passes, 9/9 tests
- `npm run build` succeeds
- `npm run dev` works; all main routes (`/`, `/accounts/acme-corp`, `/search`, `/audit`) render, and an unknown account correctly 404s
- `/search` role-sensitive behavior was manually verified against the live dev server: switching the `as` role changes the answer content, not just the UI — Account Manager does **not** receive confidential Product evidence (the answer omits it entirely), while VP Product does receive permitted Product evidence

**No backend exists yet.** Nothing below should be read as backend functionality — there is no database, API, auth, or retrieval pipeline in this repository at this time.

## Current architecture

```
app/routes (src/app/*)
    ↓
feature components (src/features/*)
    ↓
pure domain functions (src/lib/*)
    ↓
typed mock data (src/data/mockData.ts)
```

Where to look for each concern:

- **Permission filtering**: `frontend/src/lib/permissions.ts` — `canAccessEvidence` / `filterPermittedEvidence`. An evidence item is visible if the user's id is in `allowedUsers` or any of the user's `groups` intersects `allowedGroups`. This is the single chokepoint; every feature that touches evidence calls through it rather than re-implementing a check.
- **Answer construction**: `frontend/src/lib/search.ts` (`buildCommitmentAnswer`) — filters evidence first, derives citations only from the permitted set, and only reports a conflict if the conflicting evidence is itself permitted.
- **Commitment classification**: `frontend/src/lib/commitments.ts` — maps `CommitmentAuthority` to display labels and derives `RiskLevel` from status/authority/visible-conflict combinations.
- **Dashboard aggregation**: `frontend/src/lib/dashboard.ts` — per-account commitment counts (`AccountSummary`).
- **Mock data**: `frontend/src/data/mockData.ts` — all mock accounts, users, evidence, and commitments. `getUser(slug)` resolves one of three preset personas (`account-manager`, `product-manager`, `vp-product`); `currentUser` defaults to `product-manager`.
- **Domain types**: `frontend/src/types/domain.ts` — single source of truth for shared contracts (`Evidence`, `Commitment`, `UserContext`, `Account`, `AuditStage`, etc.). Extend types here first when adding a field.
- **Tests**: `frontend/tests/*.test.ts` — one file per lib module (`permissions`, `search`, `commitments`, `dashboard`), using Node's built-in test runner directly against the TypeScript sources.

Note: `/` and `/accounts/[accountId]` currently always render as `currentUser` (`product-manager`); only `/search` supports switching role via `?as=`. This is a known, accepted cosmetic inconsistency (Milestone 1 decision), not a permission-safety issue — nothing unpermitted is ever shown, the other two screens just don't expose the role switcher yet.

### Adding a backend later

Prefer a small repository interface returning the existing `frontend/src/types/domain.ts` types (example in `docs/architecture.md`) rather than reshaping components around a wire format. `docs/architecture.md` also sketches the intended future retrieval path (identity → permission resolver → ACL filter → retrieval → rerank → LLM → citations/trace) — this is documentation of intent, not something implemented in this repo yet.

## Important domain rules

- `authority` and `status` are different axes on a `Commitment` and must not be collapsed into one field. `authority` (`customer_expectation` → `sales_unapproved` → `product_target` → `product_approved` → `contractual`) says *who backed this and with what weight*; `status` (`on_track` | `at_risk` | `overdue` | `delivered`) says *where delivery stands*.
- A commitment can have both supporting evidence (`evidenceIds`) and conflicting evidence (`conflictingEvidenceIds`).
- Conflicting evidence must not be revealed — not even its existence — to a user who cannot access that evidence. A conflict badge/message may only appear if the conflicting evidence itself passed the permission filter for that user.
- Sensitivity labels (`internal` / `confidential` / `customer_shared`) are informational/display-only. They are **not** an authorization mechanism — access is decided solely by `allowedUsers`/`allowedGroups` on the evidence item.
- Role labels (e.g. "VP Product") are display-only and are **not** permission grants. Only `UserContext.groups` is consulted by the permission check.

## Development workflow

For every future milestone, follow this process:

1. Inspect existing code/docs relevant to the milestone.
2. Propose a narrowly scoped milestone.
3. List exactly which files will be created/modified.
4. Explain trade-offs and assumptions.
5. Define how the milestone will be tested/verified.
6. Stop and wait for explicit approval.
7. Implement only after approval.
8. Run tests/typecheck/build as applicable.
9. Summarize what changed.
10. Make one focused commit for the milestone.
11. Stop before beginning the next milestone.

**Do not implement multiple milestones in one pass.**

## Scope discipline

The project intentionally avoids premature infrastructure. Currently **not implemented** — do not add any of these without an explicitly approved milestone:

- Backend (no API server exists)
- PostgreSQL
- pgvector / vector search
- Embeddings
- LLM integration
- Ingestion/connectors
- Real authentication
- ACL synchronization
- Reranking
- Background queues/workers
- OpenSearch
- OpenFGA
- WorkOS

## Source-of-truth documents

Read in this order when picking up this project fresh:

1. `CLAUDE.md` (this file)
2. `PRODUCT_SPEC.md`
3. `docs/architecture.md`
4. `docs/evaluation.md`
5. `docs/sample-data-models.md`
6. `future/README.md`

## Commands

All commands run from the repo root via npm workspaces (`frontend` is the one workspace).

```bash
npm install       # install deps (Node.js 22+ required)
npm run dev       # start Next.js dev server at http://localhost:3000
npm run build     # production build
npm run typecheck # tsc --noEmit
npm test          # run domain tests
```

Tests use Node's built-in test runner against the TypeScript sources directly (`node --experimental-strip-types --test tests/*.test.ts`) — no Jest/Vitest config exists. To run a single test file from `frontend/`:

```bash
node --experimental-strip-types --test tests/permissions.test.ts
```

## Milestone status

```
Milestone 1 — Frontend scaffold verification
Status: COMPLETE

Result:
The existing frontend is installable, buildable, tested, and suitable as the
starting foundation. No code changes were required as part of Milestone 1.
```

Milestone 2 (backend foundation and data contracts) has been discussed but is **not decided** — its design should be proposed fresh in the next session following the Development workflow above, not assumed from prior conversation.

## Foreign agent configs detected

A Codex config (`~/.codex/config.toml`) and Gemini CLI config (`~/.gemini/settings.json`) exist on this machine but were not read. Reply `/import` to scan and list what's importable, then `/import --yes=<digest>` to apply.
