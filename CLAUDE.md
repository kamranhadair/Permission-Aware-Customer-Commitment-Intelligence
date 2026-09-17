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

**No backend exists yet (as of Milestone 1).** Nothing above should be read as backend functionality — there was no database, API, auth, or retrieval pipeline in this repository at that time. See "Milestone 2 — Backend foundation" below for what has since been added.

## Milestone 2 — Backend foundation (complete)

A standalone backend now exists at `backend/`, independent of search/embeddings/LLM, proving the flow: identity → org/group resolution → document ACL resolution → permitted documents → permitted chunks → commitments with permission-filtered supporting/conflicting evidence.

- Stack: FastAPI + SQLAlchemy 2.0 (sync) + PostgreSQL + Alembic + pytest, per `backend/pyproject.toml`.
- Dev-only identity: an `X-User-Id` request header, resolved against the database — the client is never trusted to assert its own org/groups/role. `role` remains display-only and is never read for authorization.
- **Single authorization chokepoint**: `backend/src/app/permissions/resolver.py`. Routers never construct ACL queries themselves (`backend/tests/test_architecture.py` is a static guardrail for this; the real proof is the behavioral tests below).
- **Account visibility is derived from document access**, not organization membership: `GET /accounts` and `GET /accounts/{slug}` only ever return accounts for which the caller has at least one permitted source document. There is no `account_acl` table.
- **Commitment visibility is derived from supporting evidence**: a commitment is only returned if at least one of its `supporting` evidence chunks is permitted. Permitted `conflicting` evidence is included: if the caller has no permitted conflicting evidence, the response contains an empty list with no separate field or flag indicating anything was withheld.
- **Tenant isolation is structural, not a duplicated `org_id` column**: `source_documents`, `chunks`, and `commitments` carry no `org_id` of their own — every resolver query reaches them by joining down from `accounts` (the only table carrying `org_id` for this lineage) with an explicit `Account.org_id == user_ctx.org_id` predicate, so a missing join fails closed (returns nothing) instead of leaking another org's data.
- A nonexistent account, a cross-org account, and a same-org account the caller has no permitted documents for all return an identical `404` — resource enumeration cannot distinguish them.
- API surface is intentionally minimal: `GET /health`, `GET /accounts`, `GET /accounts/{slug}`, `GET /accounts/{slug}/commitments`, `GET /accounts/{slug}/chunks`. No generic `/chunks/{id}` or `/evidence` endpoint.
- Tests run against a real PostgreSQL database via `TEST_DATABASE_URL` (see `backend/.env.example`), not SQLite — `backend/tests/` covers direct/group ACL grants, membership revocation, role-is-not-authorization, chunk inheritance, sensitivity having no effect on access, cross-org access (including malformed cross-org group memberships/ACLs), and every commitment-evidence visibility combination (permitted support, forbidden support, permitted/forbidden conflict, malformed cross-account evidence links).
- Environment config: `backend/.env` (gitignored, local-only) and `backend/.env.example` (committed, no real credentials). `Settings` (`backend/src/app/config.py`) loads `backend/.env` but requires `DATABASE_URL` explicitly — no hardcoded fallback — and a real shell env var always overrides the file. `backend/tests/conftest.py` forces `DATABASE_URL` to `TEST_DATABASE_URL` before any app import, so the test suite cannot accidentally touch the dev database.
- `alembic check` reports zero drift between `backend/alembic/versions/0001_create_core_schema.py` and the current models — the migration is the authoritative, verified schema, not a snapshot that can silently fall out of sync.
- **The frontend is still entirely on mock data and is not wired to this backend.** `frontend/src/data/mockData.ts` remains the source of truth for the UI; connecting them is future work.

## Milestone 3 — Ingestion foundation (complete)

A real ingestion pipeline now exists at `backend/src/app/ingestion/`, turning three local fixture source formats (support tickets, call transcripts, Slack exports) into the permission-aware `source_documents`/ACL/`chunks` rows the Milestone 2 resolver already knows how to filter. No embeddings, retrieval, commitment extraction, or real Zendesk/Gong/Slack connectors — ingestion stops at chunks.

- **Pipeline**: pure parsers (`ingestion/parsers/{support,calls,slack}.py`) produce a `NormalizedDocument` (`ingestion/types.py`) with no DB access; `ingestion/service.py` is the sole persistence boundary (parsers never touch SQLAlchemy); `ingestion/chunking.py` is a deterministic, project-owned chunker (~1000 chars, paragraph-aware, no overlap, no tokenizer dependency); `ingestion/cli.py` is a thin dev CLI (`python -m app.ingestion.cli <support|calls|slack> <path> --org-id <int>`) that only does argument parsing, I/O, and reporting.
- **Identity/idempotency**: `(account_id, source, external_id)` is the upsert key (unique constraint added in migration `0002`). Re-running the same input is a no-op (`unchanged`); unrelated `title`/`occurred_at`/`sensitivity` changes refresh on every re-ingestion even when content is unchanged; a genuine content change replaces chunks (old ones deleted, new ones inserted with a `sequence` column) unless blocked (below).
- **Legacy compatibility**: `source_documents.external_id`/`content_hash` are nullable — `NULL` on both means "predates ingestion, not source-managed" (Milestone 2 hand-seeded rows). A CHECK constraint (`ck_source_documents_ingestion_identity`) forbids the half-managed state (one set, one not). A `NULL` `external_id` can never match the upsert lookup, so ingestion can never accidentally adopt a legacy row.
- **ACL synchronization, not just resolution**: on every re-ingestion, `service.py` diffs the source's declared ACL against the currently-persisted grants and reconciles both directions (revokes what the source no longer declares, adds what it newly declares) — this is *document*-ACL sync from re-ingested source data, distinct from *group-membership* sync from a real identity provider, which remains the Milestone 2 resolver's job and is still not connected to any external IdP.
- **Security-critical ordering in `_update_document`**: ACL revocations are computed from the raw declared identities (emails/group names) and always applied, *before* any attempt to resolve newly-declared principals. An unresolvable new principal, or a content change to a document whose existing chunks are referenced by `commitment_evidence`, can defer new grants and the content/metadata/chunk update (`blocked` outcome, non-zero CLI exit) — but neither can ever leave an obsolete grant active. Missing ACL metadata (`acl=None`) is a plain rejection with no revocation inferred; an explicitly empty ACL (`{users: [], groups: []}`) persists and is visible to nobody.
- **Transactions**: one commit (or rollback) per document, owned entirely by `service.py` — the CLI has no transactional responsibility. Same-batch duplicate `(source, account_slug, external_id)` rejects the second occurrence; cross-run identity reuse is the normal upsert path.
- **Tests**: `backend/tests/test_ingestion_{parsers,service,idempotency,migration,e2e,cli}.py`, 37 tests, run against the same real-PostgreSQL `TEST_DATABASE_URL` pattern as Milestone 2. Covers all three parsers (including Slack's root/reply thread-grouping and orphan-reply rejection), user/group ACL persistence, explicit-empty-vs-missing ACL, cross-org rejection, idempotency, content-change chunk replacement, ACL add/revoke on re-ingestion, the evidence-reference block (including the revoke-anyway-despite-unresolved-principal case), migration `0002` backfill against pre-existing Milestone 2 rows, and a fixture-file (not hand-crafted) end-to-end round trip through the real resolver.
- **Fixtures**: `backend/fixtures/{support,calls,slack}/` — synthetic data only, covering multiple accounts/orgs, direct-user and group ACL grants, a confidential source inaccessible to one test user, and a cross-org account reference for rejection testing.
- Frontend untouched; still on mock data.

## Milestone 4 — Permission-aware hybrid retrieval (complete)

A retrieval layer now exists at `backend/src/app/retrieval/`, searching the chunks Milestone 3 ingested using PostgreSQL full-text search and pgvector similarity, merged via Reciprocal Rank Fusion — with authorization enforced as part of candidate generation, not as a post-search filter.

- **The core invariant**: an unauthorized chunk is never a lexical candidate, never a vector candidate, never a hybrid candidate, never returned, and never named in a user-visible trace. Both `retrieval/lexical.py` and `retrieval/vector.py` compute their permitted-chunk scope by calling the same `permissions/resolver.py` function every other permission-aware query in the codebase uses (`get_permitted_document_ids`, generalized to accept `account_id: int | None` for "all accounts visible to this user"), then apply that scope in the `WHERE` clause *before* ranking — there is no "search globally, filter in Python" step anywhere in the retrieval path.
- **Lexical retrieval**: PostgreSQL native full-text search (`to_tsvector('english', content)` / `plainto_tsquery` / `ts_rank`), backed by a GIN expression index (migration `0003`) rather than a stored `tsvector` column — nothing to backfill, nothing that can go stale relative to `content` across Milestone 3's delete+reinsert chunk replacement.
- **Vector retrieval**: pgvector, **exact (brute-force) cosine-distance search, not an approximate HNSW/IVFFlat index** (migration `0004` creates the `vector` extension and a nullable `chunks.embedding vector(384)` column, but no ANN index). This is a deliberate prototype trade-off: an approximate index's own traversal could, in principle, decide which rows are even considered before a permission predicate gets a chance to exclude them, whereas exact search evaluates the permission predicate and `embedding IS NOT NULL` against literal rows first, so there is no code path where an unauthorized or unembedded row can become a candidate. The accepted cost is brute-force scan performance at scale — explicitly not solved here.
- **Embedding provider**: one configured model, `BAAI/bge-small-en-v1.5` (384-dim), run locally via `sentence-transformers` — no external API, no API key (`backend/.env.example` is therefore unchanged). `retrieval/embeddings.py` defines a two-method `EmbeddingProvider` protocol with exactly two implementations: `BgeEmbeddingProvider` (lazy-loads the real model, never imported at module load time) and `FakeEmbeddingProvider` (deterministic, hash-seeded, pure Python) — the latter is what the entire security/functional test suite uses, so `pytest` never imports `sentence-transformers`/`torch`. The dependency is split accordingly in `pyproject.toml`: `pgvector` is a base dependency; `sentence-transformers` is behind an optional `embeddings` extra needed only for the real provider, `embed_missing`, and `evaluate.py`.
- **Embedding lifecycle**: `chunks.embedding` is nullable. New chunks and content-changed replacement chunks (Milestone 3's delete+reinsert) always start unembedded; there is no trigger and no background worker. `python -m app.retrieval.embed_missing` is an explicit, manually-run backfill command that embeds every chunk with `embedding IS NULL` in batches. An unembedded chunk is not a retrieval failure — it simply cannot become a vector candidate and remains reachable through lexical search alone until backfilled.
- **Hybrid merge**: Reciprocal Rank Fusion (`retrieval/hybrid.py`, `k=60`), chosen over score normalization because `ts_rank` and cosine distance are on incomparable scales and normalization (min-max/z-score) is unstable for small candidate sets. RRF is a pure function with no DB access, so merge determinism is unit-tested directly. Reranking beyond RRF is explicitly deferred, not added.
- **Retrieval service boundary**: `retrieval/service.py`'s `retrieve()` is the single entry point — it resolves account-slug scope through the same `get_visible_account` Milestone 2 uses (returning `None`, not a distinguishing error, for a nonexistent/cross-org/zero-permitted-document account, exactly like the existing account/commitment endpoints), calls both search channels, merges, and builds the trace.
- **Safe retrieval trace**: `RetrievalTrace` is safe by construction, not by redaction — every chunk id it contains (lexical candidates, vector candidates, merged ranking, returned ids) was already produced by a permission-scoped query, so there is no "filtered out N confidential results" computation anywhere to accidentally leak. The trace is returned in-memory/over the API response; nothing is persisted to a query-trace table in this milestone.
- **API surface**: `POST /search` (`backend/src/app/routers/search.py`), body `{query, account_slug?}`, identity via the existing dev-only `X-User-Id` header (401 without it) — the client can never assert its own role/groups/org, matching every other endpoint.
- **Result contract**: `RetrievalHit` carries only `chunk_id`, `document_id`, `account_id`, `source`, `title`, `content`, `occurred_at`, `lexical_rank`, `vector_rank`, `hybrid_score` — no ACL principals, no sensitivity label, no hidden candidate counts.
- **Tests**: `backend/tests/test_retrieval_{lexical,vector,hybrid,service,migration,quality}.py` and `test_search_api.py` — adversarially constructed (e.g. a forbidden chunk that lexically outranks, or is mathematically closer to the query vector than, the permitted chunk must still never appear as a candidate), plus direct/group ACL grants, membership/ACL revocation freshness, cross-org rejection, account-scoped vs. all-accounts privacy, no-ACL-fields-in-response, and one full ingestion-fixture-to-retrieval end-to-end round trip.
- **Retrieval-quality evaluation** (superseded by Milestone 6 — see below): originally `backend/fixtures/retrieval_eval/golden_queries.json` (10 queries) plus `python -m app.retrieval.evaluate`, computing Recall@5, Recall@10, MRR per category, and the hard security gate `unauthorized_candidate_count == 0`. Known gap at the time: no query yet empirically demonstrated hybrid fusion being *necessary* against the real embedding model (RRF's combination logic was proven at the unit level in `test_retrieval_hybrid.py` with synthetic ranks). Both the fixture file and the script were retired in Milestone 6 in favor of the unified `backend/fixtures/evaluation/golden_dataset.json` and `python -m app.evaluation.run --mode retrieval`.
- Frontend untouched; still on mock data. No LLM generation, no citations, no reranking, no persisted trace storage.

## Milestone 5 — Grounded generation + citation-safe answers (complete)

A generation layer now exists at `backend/src/app/generation/`, turning permission-scoped Milestone 4 retrieval hits plus permission-visible Milestone 2 `Commitment` rows into a structured, claim-level-cited answer via a single `POST /answer` endpoint — with server-side citation/provenance validation and zero schema migrations.

- **No reranker.** Milestone 4 deliberately stopped after RRF; Milestone 5 re-evaluated adding one and deferred it again — the bounded context (top 8 retrieval hits, all sent to the model at once, not just rank #1) already mitigates most of what a reranker would buy, and no concrete ordering-quality problem was observed. See `docs/architecture.md` for the full justification.
- **Bounded, safe-by-construction context** (`generation/context.py`): retrieval hits are kept in hybrid-rank order (never reordered by recency); permitted commitment evidence not already present is appended afterward in a deterministic `occurred_at DESC, chunk_id ASC` order; a hard cap of 10 total evidence blocks (`MAX_EVIDENCE_CONTEXT`) is enforced without ever truncating the retrieval hits themselves; a hard cap of 10 commitment blocks (`MAX_COMMITMENT_CONTEXT_BLOCKS`) applies independently. A commitment block is included only if at least one of its supporting evidence chunks survived the evidence cap — a commitment is never handed to the model with zero evidence it could legally cite.
- **Two citation id spaces**: `E1..En` (evidence, the only valid citation target) and `C1..Cn` (structured commitment context, internal-only — never a valid citation; a claim citing a `C*` id is rejected by the exact same path as an invented `E*` id).
- **Provenance-checked commitment claims**: a `Claim` carries `claim_type` (`"evidence"` or `"commitment"`) and, for `"commitment"`, a `commitment_context_id`. Server-side validation (`generation/validation.py`) requires every cited id to belong to that specific commitment's own supporting/conflicting evidence, and requires at least one cited id to come from its *supporting* evidence — citing only conflicting evidence can never by itself assert a commitment's authority or status. This makes cross-commitment authority conflation structurally impossible, not merely prompted against.
- **No public `conflict_detected` field.** A global boolean would imply stronger semantics than permitted evidence can prove (raw retrieval could surface a contradiction never linked through `commitment_evidence`). Conflict is expressed only as an ordinary grounded claim citing both a commitment's supporting and conflicting evidence together, worded as "based on the evidence available to you," never as an absolute claim that no conflict exists anywhere.
- **Precise failure semantics**: `insufficient_evidence` (a 200) means either the context was empty (model never called) or the model itself explicitly declared it. A schema-valid `"answered"` result where every claim fails grounding validation is a *different* outcome — a `GenerationFailure`, surfaced as `502 Bad Gateway` — because it proves generation failed, not that evidence was insufficient. A provider/network error is the same `GenerationFailure` → `502` path. A partial case (some claims valid, some invalid) returns `200 answered` with only the valid claims; the invalid ones are dropped and recorded (as opaque, non-sensitive ids) in the trace.
- **Structured output, not tool-simulated JSON**: one generation provider, **Google Gemini** (`google-genai`, model `gemini-2.5-flash`), using Gemini's native `response_mime_type="application/json"` + `response_schema=RawGeneratedAnswer` structured-output mode — the same Pydantic model is passed directly as the schema and used to validate the response, so the wire schema and the validation schema can never drift apart. Forced/structured output lowers malformed-output risk; it does not remove the need to validate, so every payload still goes through `parse_provider_payload` before being trusted. (The provider was chosen as Gemini per explicit instruction partway through the milestone; the original design discussion in this file's history referenced Anthropic before the swap — the tiny provider abstraction made the swap a `provider.py`-only change with zero test churn, since the whole test suite runs against `FakeAnswerGenerator`.)
- **`POST /answer`** (`backend/src/app/routers/answer.py`): body `{query, account_slug}` — `account_slug` is **required**, unlike `/search`'s optional field, since every in-scope product question is account-scoped. Identity via the existing dev-only `X-User-Id` header. `404` for a nonexistent/cross-org/zero-permitted-document account (identical, indistinguishable, matching every other endpoint); `502` for a generation failure; `200` for `answered`/`insufficient_evidence`.
- **Citation shape**: `citation_id, chunk_id, document_id, source, title, occurred_at, excerpt` — no ACL principals, no sensitivity, no hidden/filtered counts. `chunk_id`/`document_id` are kept public, matching `/search`'s existing `RetrievalHitOut` contract (not a new exposure).
- **Safe generation trace**: extends (embeds) the existing `RetrievalTrace` rather than replacing it. Adds only permission-safe, already-established-safe fields: which `E*`/`C*` ids reached the model, the generator model name, generation status, claims emitted/dropped, and the (opaque, non-sensitive) invalid ids the model attempted. The raw rendered prompt is deliberately **not** included — it would be redundant with `citations` and adds an unaudited second copy of evidence text for no benefit. Nothing is persisted to a database (unchanged from Milestone 4's stance).
- **Prompt/evidence separation**: system instructions live in the `system_instruction` parameter; retrieved content is wrapped in `<evidence>`/`<commitment>` tags in the user turn with every untrusted field angle-bracket-escaped, so retrieved text can never fabricate a closing tag or a fake citation block. The system prompt explicitly instructs that tagged content is data, never instructions. This delimiter-integrity mechanism is unit-tested directly (`tests/test_generation_prompt.py`); whether a live model actually *obeys* injected text is a claim only the manual smoke test can support (see below).
- **Tests**: `backend/tests/test_generation_{context,validation,provider,prompt,service}.py` and `test_answer_api.py` — 56 new tests, all against `FakeAnswerGenerator`/`FakeEmbeddingProvider`, no network calls. 160/160 backend tests pass overall; `permissions/resolver.py` and `retrieval/*` were not modified. Covers: unauthorized chunks never entering context/citations, group/document ACL revocation freshness, cross-org isolation, invented/cross-commitment/conflicting-only citation rejection, the zero-context short-circuit, the all-claims-invalid → `GenerationFailure` path, the partial-valid-claims path, commitment visibility/hiding parity with Milestone 2, prompt-injection delimiter escaping, and API-level 401/404/502/no-ACL-fields.
- **Generation evaluation slice** (superseded by Milestone 6 — see below): originally `backend/fixtures/generation_eval/golden_questions.json` (12 questions) plus `python -m app.generation.evaluate`. Automatically-measurable metrics were citation correctness/completeness, forbidden-evidence absence, and refusal correctness, plus the two hard security gates. Authority/conflict "correctness" deliberately reduced to the same citation-set checks rather than free-text keyword matching, because `validate_and_filter_claims` already makes cross-commitment citation structurally impossible — this design carried forward unchanged into Milestone 6's unified metrics. Claim-level factual correctness and wording quality were explicitly **not** automatically scored, also carried forward unchanged.
  - **Real-provider verification actually performed** (2026-09-16, against Gemini's free tier): a direct `GeminiAnswerGenerator` smoke test confirmed structured-output parsing and correct `GenerationFailure` wrapping of both a transient `503` and a `429` provider error. Two full runs of the 12-question eval slice together produced live, correct Gemini answers for 9 of 12 questions (the rest hit the free tier's 20-requests/day cap for `gemini-2.5-flash` and were correctly surfaced as failures, not fabricated) — across every successful call, both security gates held at zero. Observed correct behavior: sales-vs-approved authority distinction, product-target-vs-contractual distinction, a real conflicting-evidence claim citing both supporting and conflicting evidence, a permission-scoped variant of the same question correctly omitting the conflict, and correct `insufficient_evidence` abstention where no evidence existed at all. One citation-set mismatch was observed on the authority-distinction question (the model's answer was correct and grounded, but cited slightly different evidence than the golden fixture's narrower `expected_evidence` list anticipated) and one status mismatch was observed where the model answered instead of abstaining, using only permitted evidence with no fabrication — both are documented, anticipated fixture-precision gaps, not grounding or security defects. The dedicated live prompt-injection case and one live end-to-end HTTP round trip through `/answer` were prepared but not completed in this session because the free-tier daily quota was exhausted before they ran; **Milestone 6 confirmed the same quota was still exhausted on the same calendar day** — see that section below. Both the fixture file and the script were retired in Milestone 6 in favor of `backend/fixtures/evaluation/golden_dataset.json` and `python -m app.evaluation.run --mode generation`.

## Milestone 6 — Full golden evaluation + security hardening (complete)

A measurement layer now exists at `backend/src/app/evaluation/`, over everything Milestones 2–5 built: a 50-case golden dataset plus 3 permission-freshness sequences, one canonical runner (`python -m app.evaluation.run`), retiring the Milestone 4/5 `retrieval/evaluate.py` / `generation/evaluate.py` scripts and their fixture slices. Purpose: measure the full permission-aware pipeline end to end, classify any real failure before proposing a fix, and fix only what evidence justified.

- **Dataset**: `backend/fixtures/evaluation/golden_dataset.json` (50 cases across `direct_lookup` (8), `cross_doc_synthesis` (4, honestly below the nominal 10+ target — the fixture set does not support more genuinely distinct cases without padding), `conflicting_evidence` (7, same honest-count reasoning), `temporal` (8), `permission_refusal` (10), `commitment_authority` (5), `prompt_injection` (4), `insufficient_evidence` (4)) plus `permission_freshness.json` (3 mutate-query-restore sequences). Every case's evidence is a `{source, external_id}` stable reference — never a raw chunk PK — resolved at scoring time by `evaluation/stable_ids.py`, and matched at the document level (any permitted chunk of the named document satisfies a case), not the chunk level.
- **New evaluation-only fixtures** (`backend/fixtures/evaluation/{support,calls,slack}/`), ingested through the real Milestone 3 parsers and kept structurally separate from Milestone 3's own load-bearing fixtures: a new `initech-ltd` account carrying a genuine customer_expectation → product_approved → contractual timeline, a Globex timeline reversal (`product_target` → delayed), an exec-only Slack channel (the first fixture content that actually distinguishes the `exec` group from `product`), a direct-user-only grant for a new `erin` persona, and four synthetic support tickets carrying prompt-injection payloads under `injection-test-co`.
- **New personas**: `erin` (zero group membership — direct-user ACL grants only) and `frank` (a user in a *separate* organization, used only to prove cross-org isolation), alongside the existing `alice`/`bob`/`carol`/`dana`.
- **Three new hand-seeded commitments** complete authority coverage to all five values (`customer_expectation`, `product_approved`, `contractual`, alongside Milestone 5's existing `sales_unapproved`/`product_target`) — each one's supporting evidence text was written to actually justify the label (e.g. the `contractual` commitment's evidence explicitly says "per the signed MSA... a contractual commitment, not just a target"), so authority-classification scoring is a genuine check against real evidence, never a tautological check against a label the harness itself inserted.
- **Three explicit, never-blended modes**: `--mode security` (`FakeEmbeddingProvider`+`FakeAnswerGenerator`, no network, full dataset + all freshness sequences — this is also what `pytest` exercises, keeping the core suite network-free), `--mode retrieval` (real `BgeEmbeddingProvider`, no Gemini spend, real Recall@5/10/MRR), `--mode generation` (real `BgeEmbeddingProvider` + `GeminiAnswerGenerator`, quota-budgeted via `--limit`/`--start-at`/`--case-id`/`--resume`, persisting non-sensitive per-case progress to the gitignored `backend/.eval-output/`).
- **6 automated, zero-tolerance security gates** (`unauthorized_lexical_candidates`, `unauthorized_vector_candidates`, `unauthorized_hybrid_candidates`, `unauthorized_generation_context_chunks`, `unauthorized_citations`, cross-org leakage via the `account_not_visible` outcome) plus **2 gates that are deliberately human-adjudicated, not automated** (`unauthorized_facts_emitted`, `hidden_conflict_leakage`) — neither can be proven from citation ids alone (a model could imply a forbidden fact without ever citing it), and a keyword heuristic is explicitly rejected as "not a security proof." Designated cases (`conflicting_evidence`/`prompt_injection` categories) are flagged `pending_review` until a human records a verdict via `--review-case-id`/`--review-gate`/`--review-verdict`.
- **Permission-freshness sequences** mutate a real `GroupMembership`/`DocumentUserAcl` row mid-run and always restore it afterward regardless of outcome (`evaluation/freshness.py`) — proven order-independent by `test_evaluation_freshness.py` (two sequences run in either order produce identical final permission state).
- **Privilege isolation, verified not assumed**: golden-only fields (`forbidden_evidence`, `note`, `expected_conflict`, ...) never reach `GenerationContext` or the Gemini request — `test_evaluation_privilege_isolation.py` proves this with a sentinel string that must never appear in what the generator actually receives.
- **Session lifecycle, cleanup, and dataset validation** (added in a follow-up correctness pass before the baseline was trusted — see `docs/evaluation.md`'s "Bugs found and fixed"): `run()` takes an optional `db: Session`; a caller-supplied session (pytest) is used as-is and never closed, while a runner-owned session (the standalone CLI default) always attempts `cleanup.cleanup_eval_orgs()` in `finally` — success, a mid-run exception, or a validation failure all clean up the exact org that run seeded, and a cleanup failure is printed as a warning without masking the original error. `dataset_validation.py` proves every golden case's `expected_evidence`/`forbidden_evidence` against the real seeded database (resolves to exactly one document; `forbidden_evidence` is actually outside the persona's permitted set; the two never overlap) before any case is scored, replacing a "by construction" assumption with a real check. `RunReport` exposes `automated_security_all_clear` / `manual_security_review_status` / `overall_security_status` (not a single boolean) — a failing freshness sequence now correctly fails `automated_security_all_clear`, and `overall_security_status` is `"pending_review"`, not a false `"passed"`, whenever a required manual gate hasn't been adjudicated yet.
- **Security mode exercises generation structurally too** (a gap caught on further review: security mode built a `FakeAnswerGenerator` but never called it, so the full-dataset baseline never exercised context construction/citation validation, only retrieval): for every non-`retrieval_only` case, `--mode security` now runs the real `_run_generation_case_with_visibility` orchestration with a deterministic, cooperative `security_mode_fake_answer` (cites only ids it was actually given, so `validate_and_filter_claims`'s real cross-commitment-provenance branch executes on every commitment case) and `_generation_structural_gates()` (shared with real `--mode generation`, minus the answer-quality scoring on top) — a clean retrieval pass can no longer mask a generation-context/citation violation on the same case. Still reports no quality metrics and designates no case for manual review in this mode.
- **Tests**: `backend/tests/test_evaluation_{schema,metrics,security_gates,freshness,privilege_isolation,runner_fake_mode,cleanup,session_lifecycle,security_status,dataset_validation,resume,security_mode_generation,report}.py`, 63 new tests, all network-free. `test_retrieval_quality.py` was rewritten to wrap `--mode retrieval` instead of the retired `retrieval/evaluate.py`. 223/223 backend tests pass overall; `permissions/resolver.py`, `retrieval/*`, and `generation/*` were **not modified**.
- **Baseline results** (security/retrieval re-verified 2026-09-16 after all three correctness passes with identical security-relevant numbers; generation baseline extended across 2026-09-16 and 2026-09-17): `--mode security` — `overall_security_status = passed` across the full 50-case dataset and all 3 freshness sequences, now including real generation-path coverage (zero unauthorized chunks/commitment-evidence/citations across all 50 cases and all 6 personas, not just retrieval), confirmed to leave zero scratch rows in the database afterward (automatic cleanup, not manual). `--mode retrieval` (real embeddings) — `overall_security_status = passed`, Recall@5 = Recall@10 = 1.00 in every Recall-eligible category, MRR 0.80–1.00 (overall MRR 0.894 across 33 Recall-eligible cases); no retrieval bug found. `--mode generation` (real Gemini, across two calendar days) — 8 of 50 cases have reached a real terminal outcome; `overall_security_status` for this mode is honestly reported as `pending_review`, never forced to `passed`/`failed`, since no manual-review-designated case has live content yet to adjudicate. 5 live model answers (`dl-01`, `dl-02`, `dl-03`, `dl-04`, `cds-02`), zero security violations each; 4 of 5 fully correct — `cds-02` is a genuine 3-document cross-doc-synthesis success spanning the full `customer_expectation → product_approved → contractual` authority progression. `dl-03` scored `citation_correct = False`, classified as a `golden_data_problem` (the golden `expected_evidence` under-names what bob is actually, correctly, permitted to cite — see `docs/evaluation.md`), not a product bug — no fix made. 3 more (`pr-05`/`pr-07`/`pr-08`) completed structurally via the `account_not_visible` short-circuit (no model call needed). The remaining 42 were correctly recorded as `generation_failure` with zero security violations; `--resume`'s skip/retry behavior was re-verified against persisted ground truth on both days. Observed refill is a small, roughly fixed daily allotment (~1–2 live calls/day), not a fast trickle — completing all 42 remaining cases on the free tier would take many more days. The live prompt-injection case and one live end-to-end `POST /answer` round trip, both carried forward from Milestone 5, remain untried — quota, not oversight. See `docs/evaluation.md` for full detail, including why Recall/MRR are only computed for cases with real `expected_evidence` (retrieval has no relevance threshold, so `expected_evidence: []` cases would score a structurally-guaranteed 0 regardless of quality) and why `--mode security`/`retrieval` cannot check the `answered` vs. `insufficient_evidence` distinction (that judgment only exists at the generation layer).
- **This is a "Commit 1 only" milestone for product code.** Every bug found during implementation — across all three evaluation-harness correctness passes — was in the new Milestone 6 evaluation infrastructure itself (org-scoping in stable-id resolution, a composite-primary-key assumption in the freshness mutator, a flawed status heuristic in non-generation modes, missing `.env` loading in the CLI entry point, missing standalone-run cleanup, an incomplete security-status computation, unvalidated "by construction" dataset trust, and an over-eager `--resume` completion check) — none were found in the Milestone 2–5 product code, and the follow-up real-Gemini generation baseline (8/50 cases; the one imperfect result was a golden-data precision gap, not a product bug) found none either. Manufacturing a `fix:` commit against `retrieval/`, `generation/`, or `permissions/` with no evidence a fix was needed would misrepresent a clean result as a found-and-fixed one; see `docs/evaluation.md`'s "Bugs found and fixed" section for the full, honest list of what *was* found and where. The evaluation harness itself did warrant its own correctness commit, which is a different thing from tuning the product to pass the eval.
- **Known limitations**: `cross_doc_synthesis` and `conflicting_evidence` are honestly below their nominal 10+ targets (documented, not padded); the real-Gemini baseline covers 8 of 50 cases (5 live answers, 3 structural completions; quota, not a design gap) — the live prompt-injection case and one live `POST /answer` HTTP round trip, both carried over from Milestone 5, remain untried for the same reason; the two manual-review security gates, and the real-generation `overall_security_status` itself, remain `pending_review` rather than `pass`/`fail` for every designated `conflicting_evidence`/`prompt_injection` case since none of those specific categories received a live model response yet — completing this honestly requires many more free-tier quota windows or a paid tier, not a redesign; a standalone run's cleanup only runs on an ordinary Python exception path (a `finally` block) — a hard process kill between seeding and cleanup would still require manual cleanup, though this was not observed. No production-readiness claim.

## Current architecture

As of Milestone 7, the frontend is wired to the real backend for `/`, `/accounts/[slug]`, and the account page's Ask panel. `/search` calls real `POST /search`. `frontend/src/data/mockData.ts` no longer exists — see "Milestone 7" below.

```
app/routes (src/app/*)
    ↓
feature components (src/features/*)
    ↓
pure domain functions (src/lib/*)  +  server-only API/session boundary (src/lib/api/*)
    ↓
real backend (FastAPI), via server-side fetch only — never from the browser
```

Where to look for each concern:

- **Identity/session**: `frontend/src/lib/api/identity.ts` (pure, unit-tested `resolveIdentity`) and `frontend/src/lib/api/session.ts` (`server-only`; wraps it with the real cookie store and the real `GET /dev/demo-users` registry fetch). This is the single chokepoint for turning a browser-supplied demo-persona *choice* into a backend-trusted `X-User-Id` — see "Milestone 7" below for the full boundary.
- **Backend calls**: `frontend/src/lib/api/backend.ts` (`server-only`; the only place `fetch(BACKEND_URL + ...)` is called, always `cache: "no-store"`) and `frontend/src/lib/api/serverClient.ts` (`server-only`; `listAccounts`/`getAccount`/`getCommitments`/`search`/`listDemoUsers` — none take a `userId` parameter, identity is always derived internally via `session.ts`).
- **DTO → view model**: `frontend/src/lib/api/dto.ts` (backend wire shapes) and `frontend/src/lib/mapping.ts` (maps to `frontend/src/types/domain.ts` view models — performs no ACL filtering of its own; the backend has already decided what's permitted).
- **Commitment classification**: `frontend/src/lib/commitments.ts` — maps `CommitmentAuthority` to display labels and derives `RiskLevel` directly from a `CommitmentView`'s own embedded `conflictingEvidence`.
- **Dashboard aggregation**: `frontend/src/lib/dashboard.ts` — summarizes an already account-scoped `CommitmentView[]` (no client-side account filtering needed anymore).
- **Domain types**: `frontend/src/types/domain.ts` — view models for real data (`AccountView`, `CommitmentView`, `EvidenceView`, `CitationView`, `RetrievalHitView`, `DemoUserView`). These deliberately are not the old V1 mock shapes (see Milestone 7 below).
- **Tests**: `frontend/tests/*.test.ts` — pure-function coverage for `commitments`, `dashboard`, `mapping`, `session` (identity resolution), `validation` (request-body rejection), and `askReducer` (the Ask panel's race/reset state machine), all using Node's built-in test runner directly against the TypeScript sources.

### Milestone 7 — real frontend/backend integration

- **Trusted identity boundary**: the browser may pick a demo persona (that's the point of the demo), but only `src/app/actions.ts`'s `setDemoUser` Server Action ever writes the `demo_user_id` cookie (`httpOnly`), and only after checking the submitted id against the live `GET /dev/demo-users` registry. Every server-side read re-verifies that cookie's value against the same registry before treating it as a usable identity (`resolveIdentity`) — a missing, malformed, forged, or reseed-stale cookie value resolves to "unresolved," never a guessed/forced identity. `X-User-Id` is set in exactly two places: `serverClient.ts` (Server Component reads) and `src/app/api/answer/route.ts` (the one Route Handler behind the client-interactive Ask panel) — the browser never constructs it itself, and `AskAccountPanel`'s `fetch("/api/answer", ...)` body only ever contains `{query, account_slug}`.
- **No CORS, no rewrite proxy**: every FastAPI call is server-to-server (Next server → FastAPI); the browser only ever talks to the Next.js app itself. `BACKEND_URL` (`frontend/.env.local`, from `frontend/.env.example`) is server-only, never `NEXT_PUBLIC_*`.
- **`GET /dev/demo-users`**: dev/demo-only, mounted only when `ENABLE_DEMO_MODE=true` (`backend/.env`); returns only `{id, name, email, label}`, resolved from the single persistent "Demo Org" (`backend/src/app/demo/org.py`), which fails closed (500, ids logged server-side only, never guesses via `.first()`) if more than one org is ever named that.
- **Persistent demo seed**: `backend/src/app/demo/seed.py` (`python -m app.demo.seed`) — independent of `app.evaluation.*` (that module is scratch/cleanup-oriented by design); reuses only ordinary production primitives (Milestone 3 parsers/ingestion service, plain ORM models, the real embedding provider/backfill). Convergent and idempotent: reruns check each expected row by its own natural key and report `NEW`/`OK`/`FAIL` per item rather than silently no-op'ing or duplicating. Seeds one account (`acme-corp`) and two personas — Maya Chen (`account-management`) and Lena Ortiz (`product`) — telling the flagship SSO-commitment-with-a-hidden-Product-conflict story from `PRODUCT_SPEC.md`.
- **`/` and `/accounts/[slug]`** are real (`GET /accounts`, `GET /accounts/{slug}`, `GET /accounts/{slug}/commitments`); the account page embeds `AskAccountPanel` (`POST /api/answer` → `POST /answer`), rendering `answered`/`insufficient_evidence`/`not_found`/`operational_error` as four visibly distinct states (a `502` is never reworded into "no evidence exists").
- **`/search`** calls real `POST /search` server-side (a plain GET-form page, not a client fetch — no Route Handler was needed for it, unlike the Ask panel) and renders backend ordering as-is; `lexical_rank`/`vector_rank`/`hybrid_score` are stripped in `mapRetrievalHit` rather than surfaced as a ranking-debug UI.
- **`/audit`** was removed from primary navigation and left as an honest static placeholder — Milestone 4/5's retrieval/generation traces are real but were never turned into a persisted, browsable feature, and Milestone 7 did not fabricate one just because the route already existed.
- **Account fields**: the backend's `Account` model has no ARR/renewal-date/owner/segment columns — `AccountOverview` renders only `name` + the real commitment summary, not the old mock's fabricated CRM fields.
- **Evidence fields**: cards render `source`/`title`/`occurred_at`/`content` only — `sensitivity` exists on `ChunkOut` but was deliberately left unrendered (no concrete product use for it yet); `allowedUsers`/`allowedGroups`/ACL fields don't exist on any frontend type at all.
- **Citations**: rendered directly from the backend's `citations` array (server-supplied `E1`/`E2`/... labels) as a separate "Evidence" section below the answer text — no regex-parsing of answer prose, no client-side provenance engine, no `C*` internal id ever reaches a frontend type.
- **Retired**: `frontend/src/data/mockData.ts`, `frontend/src/lib/permissions.ts`, `frontend/src/lib/search.ts`, and `frontend/src/features/search/components/SearchAnswerPanel.tsx` — all had zero remaining runtime consumers once the four real routes were wired (verified by grep before deletion, not assumed).

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

- Real Zendesk/Gong/Slack API connectors and OAuth (Milestone 3 added file-based ingestion for these three source *shapes* via local fixtures — connecting to the real APIs is still not built)
- Real authentication
- ACL synchronization *from external identity/document systems* (Milestone 3 added document-ACL synchronization *from re-ingested source data* on every re-ingestion — group *membership* sync from a real identity provider is still not built; see `future/README.md` item 4)
- Reranking beyond the RRF hybrid merge (Milestone 4 added permission-aware lexical + vector retrieval with an RRF merge; Milestone 5 re-evaluated adding one for generation and deferred it again — a further reranking stage, e.g. a cross-encoder, is still not built; see `future/README.md` item 6)
- Persisted/audit query-trace storage (Milestone 4's `RetrievalTrace` and Milestone 5's `GenerationTrace` are in-memory, safe-by-construction return values, not database tables; see `future/README.md` item 9)
- A second LLM verification/entailment pass, multi-provider fallback routing, and generalized agent/tool-use orchestration (Milestone 5 deliberately used a single provider and a single generation call — see `docs/architecture.md`)
- An LLM-as-judge or any other automated proxy for free-text claim correctness / authority-wording quality (Milestone 6 evaluated and rejected this — see `docs/evaluation.md`)
- Background queues/workers
- OpenSearch
- OpenFGA
- WorkOS

pgvector, chunk embeddings, and PostgreSQL full-text search were added in Milestone 4 (`backend/src/app/retrieval/`) — these are no longer on the deferred list, but remain scoped exactly as documented there: one embedding model, exact (not approximate) vector search, no reranking. LLM generation, prompt construction, and claim-level citations were added in Milestone 5 (`backend/src/app/generation/`) — also no longer on the deferred list, scoped to one provider (Google Gemini), one generation call per request, and no persisted trace. The full 50+ question golden evaluation suite was added in Milestone 6 (`backend/src/app/evaluation/`) — also no longer on the deferred list, scoped exactly as documented there: 6 automated + 2 human-adjudicated security gates, three never-blended evaluation modes, no LLM-as-judge.

## Source-of-truth documents

Read in this order when picking up this project fresh:

1. `CLAUDE.md` (this file)
2. `PRODUCT_SPEC.md`
3. `docs/architecture.md`
4. `docs/evaluation.md`
5. `docs/sample-data-models.md`
6. `future/README.md`

## Commands

All commands run from the repo root via npm workspaces (`frontend` is the one workspace). Real data now requires the backend running (see below) with `frontend/.env.local` (copy `frontend/.env.example`) defining server-only `BACKEND_URL`.

```bash
npm install       # install deps (Node.js 22+ required)
npm run dev       # start Next.js dev server at http://localhost:3000
npm run build     # production build
npm run typecheck # tsc --noEmit
npm test          # run domain tests (network-free — no backend needed)
```

Tests use Node's built-in test runner against the TypeScript sources directly (`node --experimental-strip-types --test tests/*.test.ts`) — no Jest/Vitest config exists. To run a single test file from `frontend/`:

```bash
node --experimental-strip-types --test tests/session.test.ts
```

### Backend commands

Run from `backend/`. Requires a PostgreSQL instance and `backend/.env` (copy `backend/.env.example`) defining `DATABASE_URL` and `TEST_DATABASE_URL`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # install deps
alembic upgrade head        # apply migrations to DATABASE_URL
pytest                      # run the backend test suite against TEST_DATABASE_URL
uvicorn app.main:app --reload   # run the dev server

# Ingestion CLI (Milestone 3) — org/accounts/users/groups must already exist;
# ingestion does not provision them.
python -m app.ingestion.cli support fixtures/support/tickets.json --org-id <id>
python -m app.ingestion.cli calls   fixtures/calls/calls.json     --org-id <id>
python -m app.ingestion.cli slack   fixtures/slack               --org-id <id>

# Retrieval (Milestone 4)
# On a machine with no NVIDIA GPU, install the CPU-only torch build first —
# plain `pip install sentence-transformers` otherwise pulls PyPI's default
# CUDA-enabled torch and several GB of unused nvidia_* packages:
pip install "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev,embeddings]"      # only needed for the real (non-test) embedding provider
python -m app.retrieval.embed_missing   # backfill chunks.embedding for any chunk where it's NULL
# POST /search  {"query": "...", "account_slug": "..."}  (account_slug optional — omit to search all visible accounts)

# Generation (Milestone 5) — only needed for the real (non-test) Gemini provider:
pip install -e ".[dev,generation]"
# POST /answer  {"query": "...", "account_slug": "..."}  (account_slug required, unlike /search)

# Evaluation (Milestone 6) — the single canonical evaluation entry point,
# replacing the retired app.retrieval.evaluate / app.generation.evaluate:
python -m app.evaluation.run --mode security              # fake models, no network — full dataset + freshness sequences
python -m app.evaluation.run --mode retrieval              # real embeddings, no Gemini spend — real Recall@5/10/MRR
python -m app.evaluation.run --mode generation --limit 15  # real Gemini, quota-budgeted
python -m app.evaluation.run --mode generation --resume    # resume a quota-interrupted generation run
python -m app.evaluation.run --review-case-id ID --review-gate unauthorized_fact_emitted --review-verdict pass

# Demo (Milestone 7) — a persistent, non-scratch seed for the integrated
# frontend demo; independent of the evaluation seeding above:
ENABLE_DEMO_MODE=true  # in backend/.env — gates GET /dev/demo-users
python -m app.demo.seed                        # real embeddings (needs the `embeddings` extra)
python -m app.demo.seed --embedding-provider fake  # skip loading the real model
uvicorn app.main:app --reload  # ENABLE_DEMO_MODE=true must be set for the frontend's demo-user switcher to work
```

## Milestone status

```
Milestone 1 — Frontend scaffold verification
Status: COMPLETE

Result:
The existing frontend is installable, buildable, tested, and suitable as the
starting foundation. No code changes were required as part of Milestone 1.
```

```
Milestone 2 — Backend foundation (permission-aware schema, resolver, minimal API)
Status: COMPLETE

Result:
backend/ now exists (FastAPI + SQLAlchemy + PostgreSQL + Alembic). A single
centralized permission resolver (backend/src/app/permissions/resolver.py)
derives account visibility from document access and commitment visibility
from supporting-evidence access; tenant isolation is structural (no
duplicated org_id columns) rather than convention-maintained. 34 tests pass
against a real PostgreSQL test database (TEST_DATABASE_URL), covering direct/
group ACL grants, membership revocation, cross-org access including
malformed cross-org relational data, and every commitment-evidence
visibility combination. The frontend is untouched and still uses mock data.

Closed out with a follow-up verification pass: every security invariant
re-checked directly against the committed code (not from memory), a fresh
empty-database migration plus `alembic check` (zero drift from models), an
HTTP smoke test confirming the Account Manager / Product Manager permission
distinction, and a clean frontend regression (typecheck/tests/build).
docs/architecture.md and future/README.md updated to distinguish
implemented-now from still-future architecture.
```

```
Milestone 3 — Ingestion foundation (support tickets, call transcripts, Slack exports)
Status: COMPLETE

Result:
backend/src/app/ingestion/ now exists: three pure, DB-free parsers
(support/calls/slack) produce a NormalizedDocument consumed by a single
persistence boundary (service.py), which upserts source_documents/chunks
under a new (account_id, source, external_id) identity key, synchronizes
document ACLs on every re-ingestion, and deterministically chunks content.
Migration 0002 added external_id/content_hash (nullable, for legacy-row
compatibility, with a CHECK constraint forbidding the half-managed state)
and chunks.sequence (backfilled deterministically from existing chunk.id
order). 37 new tests pass against the real PostgreSQL test database,
covering both parsers and every security-relevant service behavior:
explicit-empty-vs-missing ACL, cross-org rejection, idempotency, content-
change chunk replacement, ACL add/revoke on re-ingestion, the evidence-
reference block, the revoke-anyway-despite-unresolved-principal case, the
migration backfill against pre-existing rows, and a fixture-file (not
hand-crafted) end-to-end round trip through the unmodified Milestone 2
resolver. 71/71 backend tests pass overall; the resolver itself was not
modified. Frontend regression (typecheck/tests/build) confirms zero
frontend changes. Manually verified against the dev database: all three
CLIs ingest cleanly with correct non-zero exit codes on cross-org/
malformed records, a second run of each produces no duplicates, and the
live API confirms the Account Manager / Product group permission
distinction on ingested (not hand-seeded) data, including a clean 404 on
the cross-org account. Design went through three review rounds before
implementation (see prior conversation for the full rationale behind each
correction — not reproduced here since the code and tests are now the
source of truth).

Key decisions, for quick reference:
- `--org-id` (integer, required) — organizations has no slug column.
- Metadata (title/occurred_at/sensitivity) refreshes on every successful
  re-ingestion regardless of whether content changed; content_hash only
  gates chunk replacement.
- ACL revocations, computed from the raw declared identities, always
  apply on an existing document — never blocked by an unresolvable new
  principal or by a content update being blocked. Only new grants and
  the content/metadata/chunk update can be deferred (`blocked` outcome).
- A content change to a document whose existing chunks are referenced by
  commitment_evidence is blocked (not committed) rather than solved with
  chunk versioning or `ON DELETE CASCADE` — an intentional Milestone 3
  limitation for a future evidence-lifecycle milestone to resolve.
- Slack documents are one per thread or one per standalone message
  (`channel_id:thread_ts` or `channel_id:ts`), grouped by locating each
  reply's root by `ts == thread_ts` (not by requiring the root to declare
  its own `thread_ts`); ACL/account/sensitivity always come from the
  parent channel.
- Missing ACL metadata (`acl=None`) is a plain rejection with no
  revocation inferred; an explicitly empty ACL persists and is visible to
  nobody.
- One commit (or rollback) per document, owned by service.py, never the
  CLI; a duplicate `(source, account_slug, external_id)` within one input
  batch rejects the second occurrence.
- Ingestion does not provision organizations/accounts/users/groups/
  memberships — those must already exist.
```

```
Milestone 4 — Permission-aware hybrid retrieval (lexical + vector + RRF merge)
Status: COMPLETE

Result:
backend/src/app/retrieval/ now exists: permission-scoped PostgreSQL full-text
search (to_tsvector/plainto_tsquery/ts_rank, GIN expression index) and
permission-scoped pgvector exact cosine-distance search (no ANN index,
migration 0004 adds the vector extension and a nullable chunks.embedding
vector(384) column), merged via Reciprocal Rank Fusion (k=60). Both search
channels compute their permitted scope through the same
get_permitted_document_ids resolver function every other permission-aware
query in the codebase uses — candidate generation itself is authorization-
constrained, not filtered afterward. A single retrieve() service boundary
(retrieval/service.py) resolves account-slug scope through the same
get_visible_account Milestone 2 uses, calls both channels, merges, and
returns a RetrievalResult with a safe-by-construction RetrievalTrace (every
id in it was already permission-scoped before the trace was built; no
"filtered out N" counts exist anywhere). One embedding provider
(BAAI/bge-small-en-v1.5, local via sentence-transformers, no API key) plus a
deterministic FakeEmbeddingProvider used by the entire test suite. A single
POST /search endpoint uses the existing dev-only X-User-Id identity
mechanism. 103/103 backend tests pass (1 additional test skipped when the
optional `embeddings` extra isn't installed, by design), including
adversarial cases (a lexically-stronger or mathematically-closer
unauthorized chunk must never become a candidate, not just be absent from
the final top-k), direct-user and group ACL grants, immediate freshness on
group-membership/document-ACL revocation, cross-org rejection, account-
scoped vs. all-accounts privacy (no inaccessible-account enumeration), no
ACL/sensitivity fields in the response, and one full ingestion-fixture-to-
retrieval end-to-end round trip. Migrations 0003/0004 verified safe against
a populated (non-empty) database and `alembic check` reports zero drift.
A 10-query retrieval-quality golden set (fixtures/retrieval_eval/) plus a
manual (non-pytest) evaluate.py script report Recall@5, Recall@10, MRR per
category, and the hard security gate unauthorized_candidate_count == 0.
Frontend untouched; still on mock data. No LLM generation, no citations, no
reranking beyond RRF, no persisted query-trace storage.

Key decisions, for quick reference:
- Exact (brute-force) vector search, not HNSW/IVFFlat: the permission
  predicate and embedding IS NOT NULL are evaluated against literal rows in
  the WHERE clause before any distance ranking, so there is no approximate-
  index-traversal step that could surface an unauthorized or unembedded row
  as a candidate. Accepted trade-off: brute-force scan cost at scale is
  explicitly not solved in this milestone.
- RRF over score normalization: ts_rank and cosine distance are on
  incomparable scales, and min-max/z-score normalization is unstable for
  small candidate sets (ties are common at prototype scale). RRF only needs
  ranks, which are always well-defined.
- Reranking beyond RRF was evaluated and deliberately deferred — proving
  permission-safe lexical+vector+hybrid retrieval independently first was
  judged more valuable than adding a reranker on spec.
- chunks.embedding is nullable; there is no trigger and no background
  worker. New chunks and content-changed replacement chunks always start
  unembedded. python -m app.retrieval.embed_missing is the explicit,
  manually-run backfill; an unembedded chunk is lexical-only, not a
  retrieval failure.
- The retrieval-quality golden set intentionally stayed at 10 queries
  (within the 8-12 target) rather than being padded — one identified gap
  (no query yet empirically proves hybrid fusion is necessary, as opposed
  to unit-testing RRF's merge logic on synthetic ranks) was documented in
  docs/evaluation.md as a candidate for the eventual full golden dataset
  rather than solved with an unverified add.
- The retrieval trace is returned in-memory/over the API response only;
  no query-trace database table was added, matching the "smallest option
  that satisfies evaluation/debuggability" guidance for this milestone.
```

```
Milestone 5 — Grounded generation + citation-safe answers
Status: COMPLETE

Result:
backend/src/app/generation/ now exists: bounded, safe-by-construction
context assembly over Milestone 4 retrieval hits and Milestone 2 permission-
visible commitments; a two-id-space citation scheme (E* evidence, C*
internal-only commitment context); server-side grounding validation that
makes cross-commitment authority conflation and conflicting-only-evidence
commitment claims structurally impossible, not merely prompted against; a
single generation provider (Google Gemini, structured JSON output, no
tool-call simulation needed); and a single new endpoint, POST /answer,
reusing the existing dev-only X-User-Id identity mechanism. 160/160 backend
tests pass overall (56 new), all against FakeAnswerGenerator/
FakeEmbeddingProvider — no network calls in pytest. Neither
permissions/resolver.py nor retrieval/* were modified. No schema migration.
Frontend untouched; still on mock data.

Design went through two review rounds before implementation: the first
added conflict/temporal/context-bound corrections (relevance-order-
preserving context, a global evidence cap, provenance-linked commitment
blocks); the second added the claim_type/commitment_context_id structured-
provenance mechanism, removed a global conflict_detected field in favor of
letting conflict emerge as an ordinary grounded claim, and drew a hard line
between "the model honestly found nothing" (insufficient_evidence, a 200)
and "the model's answer failed grounding validation" (GenerationFailure, a
502) — see prior conversation for the full rationale, not reproduced here
since the code and tests are now the source of truth.

Key decisions, for quick reference:
- No reranker: the bounded context already sends the model every
  supplied chunk (not just rank #1), muting a reranker's main benefit;
  no concrete ordering-quality problem was observed to justify the added
  dependency/complexity.
- Provider: Google Gemini (`google-genai`, model gemini-2.5-flash),
  chosen over the originally-scoped Anthropic provider per explicit
  direction partway through the milestone. The tiny provider-abstraction
  boundary meant this was a provider.py-only change with zero test
  churn — the entire test suite runs against FakeAnswerGenerator and
  never depended on which real provider was configured.
- Citation validation drops individual invalid claims rather than
  failing the whole answer; only a fully-ungrounded "answered" result
  (zero surviving claims) becomes a GenerationFailure/502 — this is a
  provider/grounding failure, deliberately never disguised as a
  legitimate insufficient_evidence business outcome.
- account_slug is required on POST /answer, unlike /search's optional
  field — every in-scope product question is account-scoped, and
  cross-account commitment aggregation is out of scope.
- Authority/conflict wording is never left to the model to invent: an
  authority word may only describe evidence backed by a [Cn] commitment
  block carrying that authority from the database.
- The full rendered prompt is excluded from the trace and the API
  response entirely — redundant with citations, and excluding it avoids
  an unaudited second copy of evidence text.
- Real-provider verification was actually run against Gemini's free
  tier (not merely designed): auth, structured-output parsing, and
  GenerationFailure wrapping of both a 503 and a 429 provider error were
  all confirmed live. Two runs of the 12-question generation-eval slice
  produced live answers for 9 of 12 questions before the free tier's
  20-requests/day cap was hit; both security gates
  (unauthorized_candidate_count, unauthorized_citation_count) held at
  zero across every successful call. The live prompt-injection case and
  one live end-to-end /answer HTTP round trip were prepared but not
  completed before quota ran out — an open follow-up, not a silently
  skipped step.
```

```
Milestone 6 — Full golden evaluation + security hardening
Status: COMPLETE

Result:
backend/src/app/evaluation/ now exists: a 50-case golden dataset plus 3
permission-freshness sequences (backend/fixtures/evaluation/) run through
one canonical entry point, python -m app.evaluation.run, retiring the
Milestone 4/5 retrieval/evaluate.py and generation/evaluate.py scripts and
their fixture slices. Three explicit, never-blended modes (security: fake
models/no network/full dataset+freshness; retrieval: real embeddings/no
Gemini spend/real Recall@5-10/MRR; generation: real Gemini/quota-budgeted/
resumable). 6 automated zero-tolerance security gates plus 2 deliberately
human-adjudicated ones (unauthorized_facts_emitted, hidden_conflict_leakage)
that a keyword heuristic cannot honestly prove. A follow-up correctness pass
(before the baseline was trusted) fixed the runner's session-ownership
contract, added automatic standalone-run cleanup (cleanup.py, invoked from
run()'s finally block, never for a caller-supplied session), replaced a
single security_all_clear boolean with three explicit fields
(automated_security_all_clear / manual_security_review_status /
overall_security_status) so a failing freshness sequence or a pending
manual gate can no longer be masked, added dataset_validation.py to prove
every golden case's forbidden_evidence against the real seeded database
instead of trusting it "by construction," and fixed --resume to retry a
generation_failure case instead of treating it as permanently done. A
third pass then fixed a deeper gap: security mode built a
FakeAnswerGenerator but never called it, so its full-dataset baseline
never exercised context construction, commitment/evidence provenance, or
citation validation at all, only retrieval. Fixed with
_score_security_generation_case (shares _generation_structural_gates()
with real --mode generation, never scores answer quality or designates
manual review) and a deterministic, cooperative security_mode_fake_answer
that cites only ids it was actually given — a retrieval_only case stays
retrieval-only, every other case now runs the real Milestone 5 generation
path structurally, and a clean retrieval pass can no longer mask a
generation-context violation on the same case.
223/223 backend tests pass overall (63 new, all network-free);
permissions/resolver.py, retrieval/*, and generation/* were not modified.
No schema migration. Frontend untouched.

Baseline (security/retrieval re-verified 2026-09-16 after all three
correctness passes with identical security-relevant numbers; generation
baseline extended across 2026-09-16 and 2026-09-17): --mode security —
overall_security_status=passed, full dataset + all 3 freshness sequences
pass, now including real generation-path coverage (zero unauthorized
chunks/commitment-evidence/citations across all 50 cases and all 6
personas), confirmed to leave zero scratch rows in the database
afterward. --mode retrieval (real BAAI/bge-small-en-v1.5) —
overall_security_status=passed, Recall@5=Recall@10=1.00 in every
Recall-eligible category (overall MRR 0.894 across 33 eligible cases);
no retrieval bug found. --mode generation (real Gemini, across two
calendar days) — 8 of 50 cases have reached a real terminal outcome (5
live model answers — dl-01, dl-02, dl-03, dl-04, cds-02, zero security
violations each; cds-02 a genuine 3-document cross-doc-synthesis success
spanning the full customer_expectation -> product_approved -> contractual
authority progression — plus 3 structural account_not_visible completions
needing no model call). 4 of the 5 live answers scored fully correct;
dl-03 scored citation_correct=False, classified as a golden_data_problem
(bob's answer correctly cited a second, genuinely relevant permitted
document — C-GLOBEX-UPDATE, the Globex timeline-reversal fixture — that
the golden expected_evidence list simply didn't name), not a product bug,
and no fix was made. The remaining 42 cases were correctly recorded as
generation_failure with zero security violations, confirmed via repeated
direct API probes outside the evaluation runner on both days; observed
refill is a small, roughly fixed daily allotment (~1-2 live calls/day),
not a fast trickle, so completing all 42 remaining cases on the free tier
would take many more days of --resume, not one more session.
overall_security_status for the real-generation mode is honestly reported
as pending_review, never forced to passed/failed, because no manual-
review-designated case (conflicting_evidence/prompt_injection) has live
content yet to adjudicate. The live prompt-injection case and one live
end-to-end POST /answer round trip, both carried over from Milestone 5,
remain untried — quota, not oversight. This is a "Commit 1 only"
milestone for product code: every bug found (across all three evaluation-
harness correctness passes) was in the new evaluation infrastructure
itself, none in the product code evaluation measured, and the follow-up
real-Gemini baseline (8/50 cases; the one imperfect result was a
golden-data precision gap, not a product bug) found none either — see
docs/evaluation.md's "Bugs found and fixed" section for the honest,
itemized list rather than a manufactured fix: commit.

Key decisions, for quick reference:
- Document-level stable identity ({source, external_id}), never a raw
  chunk PK, resolved at scoring time and org-scoped (the runner seeds a
  fresh scratch org per invocation, matching the retired scripts'
  documented not-idempotent precedent — org-scoping stable-id resolution
  is what keeps that safe across repeated runs against the same database).
- Recall@5/10/MRR are computed only for cases with a real (non-empty)
  expected_evidence set: retrieval has no relevance threshold, so a
  permission-exclusion/no-evidence-exists case would score a structurally
  guaranteed 0 regardless of quality if included, misrepresenting a metric
  artifact as a finding.
- --mode security/retrieval can only meaningfully check the
  account_not_visible outcome, never the answered/insufficient_evidence
  distinction — that judgment exists only at the generation layer (the
  model's own declaration or generation/service.py's zero-context
  short-circuit).
- Two categories (cross_doc_synthesis: 4, conflicting_evidence: 7) are
  honestly below their nominal 10+ targets rather than padded with
  near-duplicate questions — the fixture set, even after Milestone 6's new
  evaluation-only evidence, does not support more genuinely distinct cases.
- No LLM-as-judge: every invariant this project cares about (permission
  safety, citation provenance, authority conflation) is already provable
  structurally; free-text claim/wording quality stays a manual-review
  field, never an approximated score.
- Permission-freshness sequences always restore their mutation before the
  run continues, regardless of pass/fail, proven order-independent by a
  dedicated test rather than assumed from dataset ordering.
- The real-Gemini baseline remains incomplete (quota, not a design gap)
  and the architecture was explicitly not changed in response, per this
  milestone's own instruction not to redesign around free-tier limits.
- A real-generation case with an imperfect score is classified before any
  fix is considered (retrieval_failure / context_selection_failure /
  authority_provenance_failure / citation_validation_failure /
  prompt_generation_failure / golden_data_problem /
  provider_quota_failure). dl-03's citation_correct=False was a
  golden_data_problem (the fixture's expected_evidence under-named what
  was actually valid, permitted evidence) — no product code or dataset
  was changed just to make the score look better.
- overall_security_status for a real-generation run is never forced to
  passed/failed when a required manual-review gate has no live content to
  adjudicate yet; it stays pending_review honestly rather than reporting
  a false verdict in either direction.
- A caller-supplied session (db=<session>) is used exactly as given and
  never closed by the runner; a runner-owned session (the standalone CLI
  default) always attempts org-scoped cleanup in finally regardless of
  success/failure, and a cleanup failure is printed as a warning without
  ever masking the original evaluation error.
- "By construction" was not good enough for forbidden_evidence: every
  golden case's expected/forbidden stable references are now checked
  against the real seeded database (resolves to exactly one document;
  forbidden is actually outside the persona's permitted set; the two
  never overlap) before any case is scored — a malformed case aborts the
  whole run instead of silently scoring a bogus assertion.
- generation_failure (provider/network/quota error, or an all-claims-
  invalid response) is never treated as a completed result by --resume —
  only answered/insufficient_evidence/account_not_visible are. A case
  pending manual review keeps its persisted result and is never re-sent
  to the provider.
- Security mode's fake generator is deterministic and cooperative, not
  realistic: it cites only ids it was actually given, so
  validate_and_filter_claims' real cross-commitment-provenance branch
  executes on every commitment case. If it ever produces
  generation_failure, that means context/validation wiring is broken,
  not that a "model" refused — treated as a hard failure in this mode
  regardless of what the case expected.
- A retrieval_only golden case (none currently exist in the dataset, but
  the field is honored) stays retrieval-only even in security mode;
  every other case gets the full generation-path structural check.
```

```
Milestone 7 — Real frontend/backend integration
Status: COMPLETE

Result:
The Next.js frontend now runs against the real backend for /, /accounts/
[slug], and an embedded account-page "Ask about this account" panel
(POST /answer); /search calls real POST /search. Every authorization-
sensitive read is server-side (Server Components using
frontend/src/lib/api/serverClient.ts, cache: "no-store" throughout); the
one browser-facing interactive surface, the Ask panel, talks only to a
same-origin Route Handler (src/app/api/answer/route.ts) that resolves
identity from a registry-verified session cookie and rejects any request
body carrying extra fields (user_id/role/groups/org_id/...) with a 400
before it can ever reach FastAPI. The browser never constructs X-User-Id
itself. No CORS middleware was added to FastAPI and no next.config.ts
rewrite was needed — every backend call is server-to-server.

A new dev-only GET /dev/demo-users endpoint (mounted only when
ENABLE_DEMO_MODE=true) lets the frontend discover currently valid demo
identities without hardcoding database-generated ids, which are not
stable across a reseed; it fails closed (500, org ids logged server-side
only) if more than one "Demo Org" ever exists rather than guessing via
.first(). A new, persistent demo seed (backend/src/app/demo/seed.py,
backend/fixtures/demo/) is deliberately independent of
app.evaluation.{personas,fixtures_loader} — it reuses only ordinary
production primitives (Milestone 3 parsers/ingestion service, plain ORM
models, the real embedding provider) and is convergent/idempotent rather
than a one-shot script: rerunning it checks each expected row by its own
natural key and self-heals drift (e.g. a corrected account display name)
rather than silently no-op'ing or duplicating.

7 new backend tests (test_dev_identities.py, test_demo_seed.py) and 5 new/
rewritten frontend test files (session, validation, mapping, askReducer,
plus adapted commitments/dashboard tests for the new view-model shapes) —
230/230 backend tests pass, alembic check reports zero drift, 39/39
frontend tests pass, frontend typecheck and production build are clean.
mockData.ts, lib/permissions.ts, lib/search.ts, and SearchAnswerPanel.tsx
were deleted after confirming zero remaining runtime consumers by grep.

A full manual smoke was run against the real backend and the persistent
demo seed (real BAAI/bge-small-en-v1.5 embeddings): Maya Chen (account-
management) sees both demo commitments with no conflict badge; Lena Ortiz
(product) sees the same two commitments with the SSO commitment's conflict
badge visible, including the confidential Slack evidence text ("...is
exploratory...") that Maya never receives. A nonexistent account and an
unresolved-session state both render the same neutral copy, never a
permission-specific message. POST /api/answer correctly returned 401
without a session cookie, 400 for a body carrying extra user_id/role
fields (never forwarded to FastAPI), and — for a real question asked
through the full stack — a 502/operational_error, which the request log
confirmed was a genuine Gemini free-tier quota exhaustion at the backend
(POST /answer itself returned 502), not a frontend integration bug; the
Route Handler correctly surfaced this as "temporarily unavailable" rather
than mislabeling it as "no evidence exists." Per Milestone 6's already-
documented quota pattern (~1-2 live calls/day), no further live attempts
were made — automated tests do not depend on Gemini either way.

Key decisions, for quick reference:
- Identity flows browser → setDemoUser Server Action (validates the
  submitted persona id against the live demo-user registry before ever
  writing the httpOnly cookie) → server-side resolveIdentity (re-verifies
  the cookie value against that same registry on every read, so a
  forged/stale/arbitrary DB id is "unresolved," never a usable identity)
  → X-User-Id, set only in serverClient.ts and the /api/answer Route
  Handler. No cookie-signing infrastructure was added — registry
  re-verification on every read is what makes an HttpOnly cookie's mere
  presence insufficient to trust on its own.
- AskAccountPanel is keyed by `${accountSlug}:${personaId}` — a demo
  persona's numeric id is fine to use as a React identity key (it's never
  used to construct an auth header client-side), and this key change is
  what forces the panel to unmount/remount (discarding any in-flight
  request and previously rendered answer) on a persona or account switch.
- A pure askReducer (src/features/commitments/lib/askReducer.ts) makes
  the two race-safety properties — RESET always clears to idle; a
  RESOLVED for a non-current requestId is silently discarded — directly
  unit-testable without rendering anything.
- The backend's retrieval/generation trace is intentionally never
  forwarded past the Route Handler boundary and never became a frontend
  feature — "safe to return" (Milestone 4/5) is not the same claim as
  "useful product UI" for this milestone. /audit was removed from primary
  navigation and left as an honest static placeholder instead.
- Evidence cards render source/title/occurred_at/content only;
  sensitivity exists on the backend's ChunkOut but was deliberately left
  unrendered — API presence alone isn't product justification.
- Citations render as a separate "Evidence" list from the backend's own
  citation objects, never by regex-scanning answer prose for [E*] tokens
  — avoiding a second, client-side provenance interpretation engine.
- The backend's Account model has no ARR/renewal/owner/segment columns;
  the real AccountOverview renders only what the backend actually
  returns rather than preserving the old mock's fabricated CRM fields.
- "Demo Org" has no unique/slug column at the database level (adding one
  was judged out of scope — "don't modify the production schema just to
  solve demo identity"); both the seed and GET /dev/demo-users resolve it
  through one shared, tested function (app/demo/org.py) that fails closed
  on more than one match rather than each implementing its own .first().
```

## Foreign agent configs detected

A Codex config (`~/.codex/config.toml`) and Gemini CLI config (`~/.gemini/settings.json`) exist on this machine but were not read. Reply `/import` to scan and list what's importable, then `/import --yes=<digest>` to apply.
