# Permission-Aware Customer Commitment Intelligence

A deliberately narrow enterprise AI starter project for answering questions such as:

- What did we promise this customer?
- Has Product actually committed to a delivery date?
- Which customer commitments are unsupported, stale, or contradictory?

The project is **not** a generic PDF chatbot. The core architectural rule is that unauthorized evidence must be filtered **before retrieval reaches reranking or the model**.

## What is included

- `PRODUCT_SPEC.md` — the product thesis and non-negotiable principles.
- `docs/architecture.md` — intentionally simple V1 architecture and future extension points.
- `docs/evaluation.md` — golden-dataset and measurement plan.
- `docs/sample-data-models.md` — example entities and ACL-aware chunk metadata.
- `frontend/` — a Next.js + TypeScript + Tailwind scaffold backed by mock data.
- `future/README.md` — explicit list of backend pieces intentionally deferred.

## Start the frontend

Requirements: Node.js 22+ and npm.

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

### Useful commands

```bash
npm test          # pure TypeScript domain tests, no test library required
npm run typecheck # after npm install
npm run build     # production build after npm install
```

## Current scope

V1 is frontend-first. It uses typed mock providers and realistic evidence/permission models so that a real API can be connected later without redesigning the screens.

Not implemented yet: authentication, database, connectors, vector search, embeddings, ACL synchronization, reranking, or an LLM call.
