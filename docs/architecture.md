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
