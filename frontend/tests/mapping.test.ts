import test from "node:test";
import assert from "node:assert/strict";
import { mapAccount, mapCitation, mapCommitment, mapDemoUser, mapRetrievalHit } from "../src/lib/mapping.ts";
import type {
  AccountDTO,
  ChunkDTO,
  CitationDTO,
  CommitmentDTO,
  DemoUserDTO,
  RetrievalHitDTO,
} from "../src/lib/api/dto.ts";

test("mapAccount keeps only id/name", () => {
  const dto: AccountDTO = { id: "acme-corp", name: "Acme Corp" };
  assert.deepEqual(mapAccount(dto), { id: "acme-corp", name: "Acme Corp" });
});

test("mapCommitment embeds the DTO's own supporting/conflicting evidence directly, with no id/list cross-referencing", () => {
  const supporting: ChunkDTO = {
    id: 1,
    source: "call",
    title: "Acme weekly call",
    sensitivity: "customer_shared",
    occurred_at: "2026-08-12T14:30:00Z",
    content: "We will have SSO ready by November 15.",
  };
  const dto: CommitmentDTO = {
    id: 42,
    statement: "Enterprise SSO by November 15",
    promised_by: "AE",
    promise_date: "2026-08-12",
    delivery_date: "2026-11-15",
    authority: "sales_unapproved",
    status: "at_risk",
    supporting_evidence: [supporting],
    conflicting_evidence: [],
  };

  const view = mapCommitment(dto);
  assert.equal(view.id, "42");
  assert.equal(view.deliveryDate, "2026-11-15");
  assert.equal(view.supportingEvidence.length, 1);
  assert.equal(view.conflictingEvidence.length, 0);
  assert.deepEqual(view.supportingEvidence[0], {
    id: "1",
    source: "call",
    title: "Acme weekly call",
    excerpt: "We will have SSO ready by November 15.",
    occurredAt: "2026-08-12T14:30:00Z",
  });
});

test("mapped evidence never carries sensitivity, allowedUsers, allowedGroups, or accountId — those fields don't exist on the type at all", () => {
  const chunk: ChunkDTO = {
    id: 9,
    source: "slack",
    title: "Internal thread",
    sensitivity: "confidential",
    occurred_at: "2026-01-01T00:00:00Z",
    content: "internal text",
  };
  const dto: CommitmentDTO = {
    id: 1,
    statement: "S",
    promised_by: "x",
    promise_date: "2026-01-01",
    delivery_date: null,
    authority: "product_approved",
    status: "on_track",
    supporting_evidence: [chunk],
    conflicting_evidence: [chunk],
  };
  const view = mapCommitment(dto);
  for (const evidence of [...view.supportingEvidence, ...view.conflictingEvidence]) {
    assert.deepEqual(Object.keys(evidence).sort(), ["excerpt", "id", "occurredAt", "source", "title"]);
  }
});

test("mapCommitment performs no filtering — every DTO evidence item is rendered as given", () => {
  const chunk = (id: number): ChunkDTO => ({
    id,
    source: "call",
    title: `chunk ${id}`,
    sensitivity: "internal",
    occurred_at: "2026-01-01T00:00:00Z",
    content: "c",
  });
  const dto: CommitmentDTO = {
    id: 1,
    statement: "S",
    promised_by: "x",
    promise_date: "2026-01-01",
    delivery_date: null,
    authority: "contractual",
    status: "delivered",
    supporting_evidence: [chunk(1), chunk(2)],
    conflicting_evidence: [chunk(3)],
  };
  const view = mapCommitment(dto);
  assert.deepEqual(view.supportingEvidence.map((e) => e.id), ["1", "2"]);
  assert.deepEqual(view.conflictingEvidence.map((e) => e.id), ["3"]);
});

test("mapCitation surfaces the server's own E* label and never fabricates one", () => {
  const dto: CitationDTO = {
    citation_id: "E1",
    chunk_id: 5,
    document_id: 2,
    source: "call",
    title: "T",
    occurred_at: "2026-01-01T00:00:00Z",
    excerpt: "e",
  };
  const view = mapCitation(dto);
  assert.equal(view.citationLabel, "E1");
  assert.equal(view.id, "5");
});

test("mapDemoUser exposes exactly the presentation-safe fields", () => {
  const dto: DemoUserDTO = { id: 3, name: "Maya Chen", email: "maya@demo.example", label: "Account Manager" };
  assert.deepEqual(mapDemoUser(dto), dto);
  assert.deepEqual(Object.keys(mapDemoUser(dto)).sort(), ["email", "id", "label", "name"]);
});

test("mapRetrievalHit drops ranking internals (lexical_rank/vector_rank/hybrid_score/account_id)", () => {
  const dto: RetrievalHitDTO = {
    chunk_id: 1,
    document_id: 2,
    account_id: 3,
    source: "call",
    title: "T",
    content: "c",
    occurred_at: "2026-01-01T00:00:00Z",
    lexical_rank: 1,
    vector_rank: null,
    hybrid_score: 0.5,
  };
  const view = mapRetrievalHit(dto);
  assert.deepEqual(Object.keys(view).sort(), ["chunkId", "content", "documentId", "occurredAt", "source", "title"]);
});
