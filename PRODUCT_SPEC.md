# Permission-Aware Customer Commitment Intelligence — Product Spec

## Product thesis

B2B software teams make customer commitments across calls, support tickets, product work, Slack, contracts, and CRM notes. Those commitments are easy to lose, contradict, or overstate.

This product reconstructs **what was promised, by whom, with what authority, based on which evidence, and whether the organization is actually committed to delivering it**.

The first useful workflow is not “chat with all company knowledge.” It is:

> **What did we promise this customer, and is that promise actually approved?**

The primary UI is an account/commitment intelligence view. Conversational search is a supporting interface, not the whole product.

---

# 1. WHAT YOU BUILD

Build a permission-aware Customer Commitment Intelligence system that can eventually ingest fragmented enterprise data, retrieve only authorized evidence, and return cited answers.

### Conceptual source types

The full system should support at least three source types. Good initial sources are:

1. Customer call transcripts — e.g. Gong/Zoom transcripts.
2. Support tickets — e.g. Zendesk/Intercom.
3. Product work — e.g. Jira/Linear.

Later sources can include Slack, contracts/SOWs, CRM notes, internal policies, and project documents.

### Minimum chunk metadata

Every retrievable chunk needs metadata that supports filtering, authority, and freshness:

```json
{
  "chunk_id": "tix-4821-03",
  "source": "support_tickets",
  "account": "acme-corp",
  "department": "product",
  "timestamp": "2026-08-14T09:12:00Z",
  "sensitivity": "internal_confidential",
  "allowed_users": ["u17", "u39"],
  "allowed_groups": ["product", "exec"],
  "tenant_id": "company-123",
  "source_acl_version": 182,
  "permissions_synced_at": "2026-09-15T03:12:01Z"
}
```

A single `access_level` field is useful for display but is not sufficient for real access control. Real permissions are resource-specific.

### Commitment object

Do not stop at chunks. Extract a domain object that represents the customer promise:

```json
{
  "commitment_id": "com-1932",
  "account": "acme-corp",
  "statement": "SSO will be available by November 15",
  "promised_by": "Sarah Chen",
  "promised_to": "Acme Corp",
  "promise_date": "2026-08-12",
  "delivery_date": "2026-11-15",
  "type": "product_delivery",
  "authority": "sales_unapproved",
  "status": "at_risk",
  "evidence_ids": ["gong-call-1883:442-471"],
  "conflicting_evidence_ids": ["slack-C88291-19221"]
}
```

### Distinguish authority

These are not equivalent:

- Customer expectation
- Sales promise
- Product target
- Approved Product commitment
- Contractual obligation

The system should preserve those distinctions rather than flattening all retrieved text into one answer.

### V1 prototype scope

V1 intentionally uses mock data and demonstrates:

- Account overview and commitment ledger.
- Commitment status, authority, owner, due date, and evidence.
- Conflicting evidence.
- Citations/source cards.
- Confidentiality warnings.
- A search-answer experience.
- A query trace/audit view.
- Role-aware mock visibility to make the permission model tangible.

---

# 2. THE RULE THAT MATTERS

> **The model must never receive a chunk the authenticated user is not allowed to see.**

Filtering an answer after generation is too late. Sensitive context has already entered the model call.

Correct future flow:

```text
User
  ↓
Authentication
  ↓
Resolve user + group permissions
  ↓
Apply ACL filter
  ↓
Search permitted corpus only
  ↓
Hybrid retrieval
  ↓
Rerank permitted candidates only
  ↓
LLM receives permitted context only
  ↓
Grounded answer + citations
```

Permission enforcement eventually applies to:

- Retrieval candidates.
- Reranker inputs.
- LLM generation context.
- Citation visibility.
- Query traces and audit logs.

A trace must not become a second database that leaks confidential text.

### Dynamic permission constraint

Permissions may change after ingestion.

Example:

```text
09:00  Account Manager can access #product-acme.
09:10  Membership is removed.
09:11  Account Manager searches for Acme.
```

Expected result: chunks from that channel are excluded before search/reranking/generation even if they still physically exist in the index.

---

# 3. HOW YOU EVALUATE IT

Build a golden dataset of at least **50 questions**. Measure retrieval and generation separately.

Recommended distribution:

| Question type | Count |
|---|---:|
| Direct factual lookup | 8 |
| Cross-source synthesis | 10 |
| Conflicting evidence | 10 |
| Temporal/stale information | 8 |
| Permission/refusal cases | 10 |
| Commitment authority | 4 |

### Retrieval metrics

Measure whether the right evidence was found **and only permitted evidence was considered**:

- Recall@5 / Recall@10.
- MRR or nDCG.
- Permitted-chunk precision.
- Freshness/temporal correctness where applicable.

### Generation metrics

- Claim correctness.
- Citation correctness.
- Citation completeness.
- Unsupported-claim rate.
- Correct refusal rate.
- Conflict recognition.
- Authority recognition.

### Security invariants

These must remain zero across the permission test set:

```text
unauthorized chunks retrieved       = 0
unauthorized chunks reranked        = 0
unauthorized chunks sent to model   = 0
unauthorized facts emitted          = 0
```

If retrieval failed, prompt changes are not a valid fix for the retrieval problem.

---

# 4. FDE SIGNAL

The prototype should make the following engineering understanding obvious:

1. Enterprise knowledge is fragmented across systems.
2. Permissions are part of the retrieval architecture, not an output-redaction feature.
3. Retrieval quality and generation quality are separate failure layers.
4. Freshness and source authority matter for business decisions.
5. Conflicting evidence should be surfaced, not averaged away.
6. A polished answer is not automatically a trustworthy answer.
7. Every important claim should be traceable to visible evidence.
8. Logs and observability need the same permission discipline as the answer path.

The project should not look like “React + vector DB + LLM = enterprise AI.”

---

# 5. MAKE IT YOUR OWN

## Chosen domain: B2B customer commitments

The differentiating workflow is customer promise intelligence rather than horizontal enterprise search.

The system should eventually answer questions such as:

- What did we promise Acme about SSO?
- Did Product approve that date, or did Sales communicate it independently?
- Which open promises are due before renewal?
- Which promises conflict with current roadmap status?
- Which commitments are based on stale evidence?
- What can this user see about the account, and what must remain hidden?

### Example conflict

Customer call:

> AE tells the customer SSO will ship in November.

Internal Product note:

> November is exploratory; do not communicate it externally.

Jira:

> Q4 target, under review.

Expected system conclusion:

> **No verified Product commitment was found.** Sales communicated a November date, but Product evidence describes the work as exploratory and Jira lists only a target. Customer expectation therefore exceeds the internally approved commitment.

### Business-facing outcomes

Potential value should be measured with business signals, not only query volume:

- Revenue associated with at-risk commitments.
- Unsupported promises by account/team.
- Overdue customer commitments.
- Accounts with contradictory commitments.
- Renewals with unresolved promises.
- Time spent preparing account reviews.

---

# Deliberately deferred from V1

To avoid over-engineering, V1 does **not** implement:

- Database or ORM.
- Backend APIs.
- OAuth/SSO.
- Real enterprise connectors.
- Vector database or embeddings.
- ACL synchronization service.
- Reranking infrastructure.
- LLM integration.
- Queues/workers.
- Redis.
- Kubernetes/microservices.
- Billing/org administration.

The frontend should expose clean boundaries so these can be attached later.
