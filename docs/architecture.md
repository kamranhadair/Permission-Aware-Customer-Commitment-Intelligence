# Architecture — Simple First, Permission-Correct Later

## V1

V1 is a frontend-first prototype with typed mock data.

```text
Next.js UI
  ├─ Accounts feature
  ├─ Commitments feature
  ├─ Search feature
  └─ Audit feature
        ↓
Typed mock repositories/data
        ↓
Pure domain helpers
```

No backend is simulated with unnecessary HTTP layers. The goal is to make the product workflow concrete while preserving interfaces and types that can map cleanly to an API later.

## Future retrieval path

```text
Identity provider
      ↓
Permission resolver
      ↓
ACL filter/query constraints
      ↓
Keyword + vector retrieval
      ↓
Merge + rerank
      ↓
Authority/conflict resolution
      ↓
LLM generation
      ↓
Citations + trace
```

The ACL constraint belongs before retrieval. A forbidden chunk should not appear in candidate lists, reranker inputs, generation context, citations, or user-visible trace content.

### What Milestone 2 actually implemented

The diagram above described this whole path as future work. As of Milestone 2 (`backend/`), the first two stages are real, not hypothetical — the rest remain future:

```text
IMPLEMENTED NOW
identity injection (dev-only X-User-Id header)
  → DB user/org/group resolution (never trusts the request for roles/groups)
  → permission resolver (backend/src/app/permissions/resolver.py)
  → ACL-filtered accounts/documents/chunks
  → permission-derived commitment/evidence visibility
    (a commitment is only returned if ≥1 of its supporting evidence chunks
    is permitted; forbidden conflicting evidence is omitted without a
    trace of its existence)

STILL FUTURE
keyword/vector retrieval
  → reranking
  → authority/conflict resolution beyond evidence-visibility gating
  → LLM generation
  → citations/query-trace pipeline
  → a real enterprise identity provider (X-User-Id is dev-only, not auth)
```

Tenant isolation (`accounts.org_id` is the only place org is recorded; documents/chunks/commitments have no `org_id` of their own and are reached only by joining down from `accounts`) and account/commitment visibility being *derived* from document/evidence access, rather than granted by org or account membership, are both implemented now and covered by `backend/tests/`.

### What Milestone 3 actually implemented

Milestone 3 (`backend/src/app/ingestion/`) sits *upstream* of the diagram above — it's what populates `source_documents`/ACLs/`chunks` in the first place, not a change to the request-time resolver path:

```
IMPLEMENTED NOW (in addition to Milestone 2's list)
source-specific parsing (support tickets, call transcripts, Slack exports
  — local fixtures, not real connectors)
  → normalized document + ACL declaration
  → account/principal resolution against the same org-scoped tables the
    resolver reads
  → idempotent upsert keyed on (account_id, source, external_id)
  → document-ACL synchronization from the source's declared ACL on every
    re-ingestion (add what's newly granted, revoke what's no longer
    declared — safe revocations always apply even when a new grant or a
    content update is blocked)
  → deterministic chunking, replaced wholesale on a genuine content
    change (unless blocked by an evidence reference — see CLAUDE.md's
    Milestone 3 status block)

STILL FUTURE (unchanged)
real Zendesk/Gong/Slack API connectors and OAuth
  → keyword/vector retrieval
  → reranking
  → authority/conflict resolution beyond evidence-visibility gating
  → LLM generation
  → citations/query-trace pipeline
  → a real enterprise identity provider
  → group-membership sync from that provider (ingestion syncs *document*
    ACLs from source data; the resolver still owns group membership, and
    nothing syncs that membership from an external system)
```

### What Milestone 4 actually implemented

Milestone 4 (`backend/src/app/retrieval/`) is the next stage of the diagram at the top of this section — the first retrieval implementation, sitting downstream of everything Milestone 2/3 built:

```
IMPLEMENTED NOW (in addition to Milestone 2's and Milestone 3's lists)
permission-scoped PostgreSQL full-text search (lexical channel)
  → permission-scoped pgvector exact cosine-distance search (vector channel,
    no approximate/ANN index — see below)
  → both channels compute candidate scope via the same
    get_permitted_document_ids resolver function Milestone 2 already uses
    for every other permission-aware query — authorization is part of
    candidate generation, not a filter applied after search
  → Reciprocal Rank Fusion hybrid merge (k=60) of the two channels
  → a single retrieve() service boundary, reusing get_visible_account for
    account-slug scoping/404 parity
  → a safe-by-construction in-memory RetrievalTrace (every id in it was
    already permission-scoped before the trace was built — there is no
    redaction step, and no "N results filtered out" count exists anywhere)
  → one embedding provider (BAAI/bge-small-en-v1.5, local, no API key) plus
    a deterministic fake provider used by the whole test suite
  → an explicit, manually-run embedding backfill command
    (python -m app.retrieval.embed_missing) — no trigger, no background
    worker
  → a single POST /search endpoint using the existing dev-only X-User-Id
    identity mechanism
  → a small (10-query) retrieval-quality golden set and evaluation script
    reporting Recall@5/10, MRR, and a hard unauthorized-candidate-count == 0
    gate

STILL FUTURE (unchanged by Milestone 4)
reranking beyond the RRF hybrid merge, if still judged necessary
  → LLM generation
  → citations/claim grounding
  → a persisted/audit query-trace store (the current trace is an in-memory
    return value, not a database table)
  → the full 50+ question golden evaluation suite covering generation
    metrics, not just retrieval
  → real Zendesk/Gong/Slack API connectors and OAuth
  → a real enterprise identity provider
  → group-membership sync from that provider
```

**The pgvector exact-vs-approximate trade-off, explained**: this milestone uses exact (brute-force) nearest-neighbor search — no HNSW/IVFFlat index exists on `chunks.embedding`. The reason is specifically about the security invariant, not just simplicity: an approximate index's own traversal logic decides which rows are even visited before any other predicate runs, so if a permission filter were layered on *after* that traversal, an approximate index could in principle cause an authorized result to be silently dropped (a recall problem) without ever being able to leak an unauthorized one — but proving that boundary precisely for a given ANN implementation is nontrivial, and this prototype avoids the question entirely by never introducing an approximate traversal step. In this design, the permission predicate and `embedding IS NOT NULL` are evaluated against literal rows in the `WHERE` clause before `ORDER BY`/`LIMIT` ranks anything, so there is no code path — approximate or otherwise — where an unauthorized row can become a candidate. The accepted trade-off is brute-force scan cost at scale; this is a deliberate prototype-scope decision, not a claim of production-scale performance.

### What Milestone 5 actually implemented

Milestone 5 (`backend/src/app/generation/`) is the next stage of the diagram at the top of this section — grounded generation and citations, sitting downstream of everything Milestone 2/3/4 built:

```
IMPLEMENTED NOW (in addition to Milestone 2's, 3's, and 4's lists)
bounded, safe-by-construction context assembly over retrieval hits + visible
  commitments (retrieval hits kept in hybrid-rank order, commitment evidence
  appended deterministically, hard caps on both evidence and commitment
  block counts — backend/src/app/generation/context.py)
  → a two-id-space citation scheme: E* (evidence, the only valid citation
    target) and C* (structured commitment context, internal-only — never a
    valid citation)
  → server-side grounding validation (generation/validation.py) that makes
    cross-commitment authority conflation, and asserting a commitment's
    authority/status from conflicting-only evidence, structurally
    impossible rather than merely prompted against
  → one generation provider (Google Gemini, structured JSON output via
    response_schema, no tool-call simulation) plus a deterministic fake
    generator used by the entire test suite
  → a single retrieve-then-generate service boundary
    (generation/service.py:answer()), reusing retrieve() and
    get_visible_commitments() unmodified — no new ACL query was written
  → a precise failure taxonomy: insufficient_evidence (a legitimate 200,
    either a deterministic zero-context short-circuit or the model's own
    declaration) is kept structurally distinct from GenerationFailure (a
    502) — the latter covers both provider/network errors and a
    schema-valid "answered" result where every claim fails grounding
    validation, since that proves generation failed, not that evidence was
    insufficient
  → a single new endpoint, POST /answer, reusing the existing dev-only
    X-User-Id identity mechanism, with account_slug required (unlike
    /search's optional field)
  → a safe generation trace that extends (embeds) the existing
    RetrievalTrace rather than replacing it, and deliberately excludes the
    raw rendered prompt
  → a 12-question generation-focused evaluation slice
    (fixtures/generation_eval/) and a manual eval script mirroring
    retrieval/evaluate.py's shape

STILL FUTURE
reranking beyond the RRF hybrid merge, if still judged necessary
  → a second LLM verification/entailment pass beyond citation-ID and
    provenance validation (deliberately deferred — see below)
  → a persisted/audit query-trace store (still an in-memory return value)
  → the full 50+ question golden evaluation suite
  → real Zendesk/Gong/Slack API connectors and OAuth
  → a real enterprise identity provider
  → group-membership sync from that provider
```

**Why reranking stayed deferred for generation too**: Milestone 5's context bound sends the model every one of the (up to 8) retrieval hits at once, not just the top-ranked one — a reranker's main value, surfacing the single best passage, is largely already mitigated when the model sees the whole window and reasons across it. No query in the generation eval slice demonstrated the model getting confused by irrelevant chunks crowding out a relevant one within that window. This is a re-evaluation, not a rubber-stamp of Milestone 4's original decision — revisit if a future eval slice shows otherwise.

**Why claim-level structured provenance instead of trusting citation-ID validity alone**: a claim can cite a real, valid evidence id and still not actually support what it asserts — citation-ID validation alone cannot catch a claim that cites commitment A's evidence while describing commitment B's authority. Rather than trying to infer this from free-text prose (fragile) or adding a second LLM entailment/verification call (doubling the architecture for a single milestone), the model itself is asked to emit `claim_type` and, for commitment claims, `commitment_context_id` as part of the same structured output — one generation call, and the provenance check becomes a deterministic set-membership comparison. Free-text claim *correctness* (does the sentence say the right thing) is not solved by this and is not automatically scored; see `docs/evaluation.md`.

**Why no public `conflict_detected` field**: a boolean computed from "does any visible commitment have permitted conflicting evidence" would imply a stronger guarantee than the system can prove — raw retrieval could surface a contradiction between two chunks never linked through `commitment_evidence`, which such a flag would silently miss while still looking authoritative. Conflict is instead expressed only as an ordinary grounded claim, citing both a commitment's supporting and conflicting evidence together, worded as "based on the evidence available to you" rather than as an absolute claim.

## Frontend feature boundaries

- `features/accounts` owns account-level presentation.
- `features/commitments` owns commitment cards and authority/risk presentation.
- `features/search` owns the grounded Q&A experience.
- `features/audit` owns a safe trace representation.
- `lib` contains domain functions, including permission filtering and summary calculations.
- `data` contains replaceable mock records only.
- `types` contains shared domain contracts.

## Backend attachment point

A backend now exists (`backend/`, see Milestone 2 status above), but the frontend is not wired to it yet — that remains future work, deliberately out of scope for Milestone 2. When that wiring happens, prefer a small API client/repository layer that returns the existing domain types. Avoid rewriting components around backend response shapes.

Example future boundary:

```ts
interface CommitmentRepository {
  listByAccount(accountId: string): Promise<Commitment[]>;
}
```

The frontend does not need this interface until it is actually being wired to the backend; adding layers solely for hypothetical flexibility is intentionally avoided.

Note that the backend's response contracts already differ from `frontend/src/types/domain.ts` in two deliberate ways worth resolving at wiring time: `Evidence.allowedUsers`/`allowedGroups` are not exposed over the API (ACL membership is server-side authorization data), and a commitment's evidence comes back embedded and pre-filtered (`supporting_evidence`/`conflicting_evidence` as full objects) rather than as `evidenceIds`/`conflictingEvidenceIds` arrays, since there is no generic evidence-by-id endpoint to resolve them against.
