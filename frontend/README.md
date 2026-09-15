# Frontend

Next.js App Router prototype for Permission-Aware Customer Commitment Intelligence.

## Run

From the repository root:

```bash
npm install
npm run dev
```

Or from this folder:

```bash
npm install
npm run dev
```

Routes:

- `/` — commitment dashboard.
- `/accounts/acme-corp` — account intelligence and permitted evidence.
- `/search` — grounded mock answer; switch roles to see ACL-aware evidence changes.
- `/audit` — safe query trace and permission boundary.

## Important

The UI is backed by mock records in `src/data/mockData.ts`. Permission filtering is real prototype logic in `src/lib/permissions.ts`, but there is no authentication or backend yet.
