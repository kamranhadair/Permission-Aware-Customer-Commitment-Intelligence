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

## Frontend feature boundaries

- `features/accounts` owns account-level presentation.
- `features/commitments` owns commitment cards and authority/risk presentation.
- `features/search` owns the grounded Q&A experience.
- `features/audit` owns a safe trace representation.
- `lib` contains domain functions, including permission filtering and summary calculations.
- `data` contains replaceable mock records only.
- `types` contains shared domain contracts.

## Backend attachment point

When a backend is added, prefer a small API client/repository layer that returns the existing domain types. Avoid rewriting components around backend response shapes.

Example future boundary:

```ts
interface CommitmentRepository {
  listByAccount(accountId: string): Promise<Commitment[]>;
}
```

V1 does not need this interface until there is an actual backend implementation to swap in; adding layers solely for hypothetical flexibility is intentionally avoided.
