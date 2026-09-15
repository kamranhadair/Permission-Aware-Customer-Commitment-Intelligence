# Commitment Intelligence V1 Design

## Goal

Produce a frontend-first, permission-aware Customer Commitment Intelligence prototype that makes the product thesis and critical security invariant visible without implementing speculative backend infrastructure.

## Design

The app is a Next.js + TypeScript + Tailwind UI backed by typed mock records. Four screens demonstrate the product: a dashboard, account detail, grounded search answer, and safe query trace. Domain helpers filter evidence by user/group ACLs and calculate account/commitment summaries.

The UI must make the distinction between sales promises, Product targets, approved Product commitments, and contractual obligations explicit. Confidential evidence that is not permitted for the selected user is excluded by the domain filtering helper before any answer/trace data is assembled.

## Non-goals

No database, real authentication, external connectors, vector database, embeddings, reranker, queues, or LLM calls in V1.

## Verification

Use Node's built-in TypeScript test execution for core domain behavior. Verify the packaged file tree and configuration. A full Next.js production build requires installing npm dependencies after download.
