# Deferred Backend Work

This folder is a reminder of what is intentionally **not** implemented in V1.

Add these only when you are ready to build the real data plane:

1. Authentication and identity provider integration.
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
6. Hybrid retrieval and reranking.
7. Commitment extraction/normalization pipeline.
8. Citation-safe generation service.
9. Permission-safe query trace/audit storage.
10. Golden-dataset evaluation runner.

Do not add a service merely because it appears on this list. Add the smallest component that solves the next validated requirement.
