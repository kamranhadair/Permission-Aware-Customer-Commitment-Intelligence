# Deferred Backend Work

This folder is a reminder of what is intentionally **not** implemented in V1.

Add these only when you are ready to build the real data plane:

1. Authentication and identity provider integration.
2. Source connectors and ingestion jobs.
3. Normalization/chunking pipeline.
4. Resource ACL *synchronization* from external identity/document systems.
   (Note: the permission resolver itself — resolving a user's org/group
   principals and filtering documents/chunks/commitments by ACL — is
   implemented as of Milestone 2, `backend/src/app/permissions/resolver.py`.
   What's still deferred here is syncing ACLs *from* real external
   systems; ACLs are currently written directly, not synced.)
5. Keyword + vector index.
6. Hybrid retrieval and reranking.
7. Commitment extraction/normalization pipeline.
8. Citation-safe generation service.
9. Permission-safe query trace/audit storage.
10. Golden-dataset evaluation runner.

Do not add a service merely because it appears on this list. Add the smallest component that solves the next validated requirement.
