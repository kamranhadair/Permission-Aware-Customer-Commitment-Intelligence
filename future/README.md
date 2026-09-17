# Deferred Backend Work

This folder is a reminder of what is intentionally **not** implemented in V1.

Add these only when you are ready to build the real data plane:

1. Authentication and identity provider integration.
   (Note: as of Milestone 7, the frontend has a trusted *demo-persona
   switcher* — a Server Action validates a browser-chosen persona against
   a dev-only registry before setting an httpOnly session cookie, and
   every server-side read re-verifies that cookie against the registry
   before deriving X-User-Id. This is still not real authentication: there
   is no login, no password/token, and any of the seeded demo personas can
   be chosen by anyone who can reach the app. See CLAUDE.md's Milestone 7
   section and `backend/src/app/routers/dev_identities.py`.)
2. Source connectors and ingestion jobs.
   (Note: as of Milestone 3, `backend/src/app/ingestion/` implements the
   ingestion *pipeline* — parsing, normalization, idempotent persistence,
   deterministic chunking, a dev CLI — against local fixture files for
   three source shapes (support tickets, call transcripts, Slack
   exports). What's still deferred here is the *connector* half: real
   Zendesk/Gong/Slack API clients, OAuth, and any scheduled/background
   job to run ingestion automatically.)
3. Normalization/chunking pipeline.
   (Implemented as of Milestone 3 — see `ingestion/types.py` and
   `ingestion/chunking.py`. Deterministic, no embeddings, no overlap.)
4. Resource ACL *synchronization* from external identity/document systems.
   (Note: the permission resolver itself — resolving a user's org/group
   principals and filtering documents/chunks/commitments by ACL — is
   implemented as of Milestone 2, `backend/src/app/permissions/resolver.py`.
   As of Milestone 3, `backend/src/app/ingestion/service.py` also
   synchronizes a *document's* ACL rows from that document's own source
   data on every re-ingestion (grants added/revoked to match the latest
   declaration). What's still deferred here is syncing *group membership*
   from a real external identity provider — that's a different sync
   problem, and nothing in this repository connects to a real IdP yet.)
5. Keyword + vector index.
   (Implemented as of Milestone 4 — `backend/src/app/retrieval/{lexical,vector}.py`.
   PostgreSQL full-text search via a GIN expression index over
   `to_tsvector('english', content)`, and pgvector exact cosine-distance
   search over a nullable `chunks.embedding vector(384)` column, both scoped
   by the same permission resolver used everywhere else. No approximate
   (HNSW/IVFFlat) index — a deliberate trade-off, see `docs/architecture.md`.)
6. Hybrid retrieval and reranking.
   (Hybrid merge implemented as of Milestone 4 — `backend/src/app/retrieval/hybrid.py`,
   Reciprocal Rank Fusion, k=60. Reranking beyond RRF — e.g. a cross-encoder —
   remains deferred; Milestone 4 deliberately proved permission-safe
   lexical+vector+hybrid retrieval first rather than adding a reranker on
   spec, and Milestone 5 re-evaluated the question for generation and
   deferred it again since the bounded context already sends the model
   every retrieved chunk, not just the top-ranked one.)
7. Commitment extraction/normalization pipeline.
8. Citation-safe generation service.
   (Implemented as of Milestone 5 — `backend/src/app/generation/`. Bounded
   context assembly over permission-scoped retrieval hits and visible
   commitments, structured claim-level citations with server-side
   provenance validation, and a single Google Gemini provider behind a
   tiny abstraction. What's still deferred: a reranker, a second LLM
   verification/entailment pass, and multi-provider fallback — see
   `docs/architecture.md`'s "What Milestone 5 actually implemented".)
9. Permission-safe query trace/audit storage, and a frontend audit UI.
   (Partially addressed as of Milestone 4/5: `retrieval/service.py` and
   `generation/service.py` return in-memory `RetrievalTrace`/
   `GenerationTrace` objects that are safe by construction — every id in
   them was already permission-scoped before the trace was built, with no
   "filtered out N" counts anywhere, and the raw rendered generation prompt
   is deliberately excluded. What's still deferred is *storage*: no
   query-trace database table exists for either stage. As of Milestone 7,
   the frontend's `/api/answer` Route Handler doesn't even forward the
   trace it receives to the browser, and `/audit` was removed from primary
   navigation in favor of an honest placeholder — "safe to return" was
   judged not to be the same claim as "useful product UI" without a real
   persisted store to browse. A real trace-inspection UI is a future
   decision, not something to fabricate ahead of that storage existing.)
10. Golden-dataset evaluation runner.
    (Implemented as of Milestone 6 — `backend/src/app/evaluation/`, a single
    canonical `python -m app.evaluation.run` entry point retiring the
    Milestone 4/5 `retrieval/evaluate.py` / `generation/evaluate.py`
    scripts. A 50-case golden dataset plus 3 permission-freshness sequences
    (`backend/fixtures/evaluation/`), three explicit modes (security/
    retrieval/generation, never blended into one score), 6 automated
    zero-tolerance security gates plus 2 human-adjudicated ones, and
    quota-aware resume for the real-Gemini mode. See `docs/evaluation.md`
    for the full dataset composition, metrics, gates, and baseline results.
    What's still deferred: a completed real-Gemini baseline across the full
    dataset (blocked by the free tier's daily quota, not a design gap) and
    an LLM-as-judge or any other automated proxy for free-text claim/wording
    quality — deliberately not built, matching Milestone 5's own reasoning.)
11. CRM-style account enrichment (ARR, renewal date, owner, segment).
    (These existed only in the Milestone 1 mock data; the backend's
    `Account` model (`backend/src/app/models/account.py`) has never had
    such columns. Milestone 7's real `AccountOverview` renders only
    `name` plus the real commitment summary rather than preserving the
    old mock's fabricated fields. Add real columns/an enrichment source
    only against an actual validated need, not to restore V1's look.)

Do not add a service merely because it appears on this list. Add the smallest component that solves the next validated requirement.
