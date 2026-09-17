import test from "node:test";
import assert from "node:assert/strict";
import { getCommitmentLabel, getCommitmentRisk } from "../src/lib/commitments.ts";
import type { CommitmentView, EvidenceView } from "../src/types/domain.ts";

const base: CommitmentView = {
  id: "1",
  statement: "Statement",
  promisedBy: "Someone",
  promiseDate: "2026-01-01",
  authority: "sales_unapproved",
  status: "on_track",
  supportingEvidence: [],
  conflictingEvidence: [],
};

const conflictEvidence: EvidenceView = {
  id: "e1",
  source: "slack",
  title: "Internal thread",
  excerpt: "not approved",
  occurredAt: "2026-01-01T00:00:00Z",
};

test("getCommitmentLabel gives each authority a distinct human-readable label", () => {
  assert.equal(getCommitmentLabel("customer_expectation"), "Customer expectation");
  assert.equal(getCommitmentLabel("sales_unapproved"), "Sales promise · unapproved");
  assert.equal(getCommitmentLabel("product_target"), "Product target · not committed");
  assert.equal(getCommitmentLabel("product_approved"), "Product commitment · approved");
  assert.equal(getCommitmentLabel("contractual"), "Contractual obligation");
});

test("overdue is always high risk regardless of authority or conflict", () => {
  assert.equal(getCommitmentRisk({ ...base, status: "overdue", authority: "contractual" }), "high");
});

test("sales_unapproved with a visible (already-permitted) conflict is high risk", () => {
  assert.equal(
    getCommitmentRisk({ ...base, authority: "sales_unapproved", status: "on_track", conflictingEvidence: [conflictEvidence] }),
    "high",
  );
});

test("sales_unapproved with no conflict and not at_risk is not automatically high", () => {
  assert.equal(getCommitmentRisk({ ...base, authority: "sales_unapproved", status: "on_track" }), "low");
});

test("at_risk status alone is medium", () => {
  assert.equal(getCommitmentRisk({ ...base, authority: "product_approved", status: "at_risk" }), "medium");
});

test("product_target authority alone is medium", () => {
  assert.equal(getCommitmentRisk({ ...base, authority: "product_target", status: "on_track" }), "medium");
});

test("on_track, no conflict, approved authority is low risk", () => {
  assert.equal(getCommitmentRisk({ ...base, authority: "product_approved", status: "on_track" }), "low");
});

test("risk reads the commitment's own embedded conflictingEvidence — an empty array (no conflict, or one this caller can't see) is never treated as risky by itself", () => {
  assert.equal(
    getCommitmentRisk({ ...base, authority: "product_approved", status: "on_track", conflictingEvidence: [] }),
    "low",
  );
});
