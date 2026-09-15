import test from "node:test";
import assert from "node:assert/strict";
import { getAccountSummary } from "../src/lib/dashboard.ts";
import type { Commitment } from "../src/types/domain.ts";

const commitments: Commitment[] = [
  { id: "1", accountId: "acme", statement: "A", promisedBy: "x", promiseDate: "2026-01-01", authority: "sales_unapproved", status: "at_risk", evidenceIds: [], conflictingEvidenceIds: [] },
  { id: "2", accountId: "acme", statement: "B", promisedBy: "x", promiseDate: "2026-01-01", authority: "product_approved", status: "overdue", evidenceIds: [], conflictingEvidenceIds: [] },
  { id: "3", accountId: "acme", statement: "C", promisedBy: "x", promiseDate: "2026-01-01", authority: "contractual", status: "delivered", evidenceIds: [], conflictingEvidenceIds: [] },
  { id: "4", accountId: "other", statement: "D", promisedBy: "x", promiseDate: "2026-01-01", authority: "sales_unapproved", status: "at_risk", evidenceIds: [], conflictingEvidenceIds: [] }
];

test("summarizes only the selected account", () => {
  assert.deepEqual(getAccountSummary("acme", commitments), {
    total: 3,
    open: 2,
    unsupported: 1,
    atRisk: 1,
    overdue: 1,
    delivered: 1,
  });
});
