import test from "node:test";
import assert from "node:assert/strict";
import { getCommitmentLabel, getCommitmentRisk } from "../src/lib/commitments.ts";
import type { Commitment, Evidence } from "../src/types/domain.ts";

const commitment: Commitment = {
  id: "com-1",
  accountId: "acme-corp",
  statement: "SSO by November 15",
  promisedBy: "Sarah Chen",
  promiseDate: "2026-08-12",
  deliveryDate: "2026-11-15",
  authority: "sales_unapproved",
  status: "at_risk",
  evidenceIds: ["ev-call"],
  conflictingEvidenceIds: ["ev-slack"],
};

const evidence: Evidence[] = [
  {
    id: "ev-call",
    source: "call",
    accountId: "acme-corp",
    title: "Customer call",
    excerpt: "We will have SSO by November.",
    department: "sales",
    timestamp: "2026-08-12T14:30:00Z",
    sensitivity: "customer_shared",
    allowedUsers: [],
    allowedGroups: ["sales"],
  },
  {
    id: "ev-slack",
    source: "slack",
    accountId: "acme-corp",
    title: "Product leadership thread",
    excerpt: "November is exploratory; do not commit externally.",
    department: "product",
    timestamp: "2026-08-14T09:12:00Z",
    sensitivity: "confidential",
    allowedUsers: [],
    allowedGroups: ["product", "exec"],
  },
];

test("renders a clear authority label for an unapproved sales promise", () => {
  assert.equal(getCommitmentLabel("sales_unapproved"), "Sales promise · unapproved");
});

test("rates a conflicting unapproved promise as high risk", () => {
  assert.equal(getCommitmentRisk(commitment, evidence), "high");
});
