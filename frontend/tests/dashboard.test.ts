import test from "node:test";
import assert from "node:assert/strict";
import { getAccountSummary } from "../src/lib/dashboard.ts";
import type { CommitmentView } from "../src/types/domain.ts";

function commitment(overrides: Partial<CommitmentView>): CommitmentView {
  return {
    id: "1",
    statement: "S",
    promisedBy: "x",
    promiseDate: "2026-01-01",
    authority: "sales_unapproved",
    status: "at_risk",
    supportingEvidence: [],
    conflictingEvidence: [],
    ...overrides,
  };
}

test("summarizes an already account-scoped commitment list (GET /accounts/{slug}/commitments is inherently scoped)", () => {
  const commitments = [
    commitment({ id: "1", authority: "sales_unapproved", status: "at_risk" }),
    commitment({ id: "2", authority: "product_approved", status: "overdue" }),
    commitment({ id: "3", authority: "contractual", status: "delivered" }),
  ];
  assert.deepEqual(getAccountSummary(commitments), {
    total: 3,
    open: 2,
    unsupported: 1,
    atRisk: 1,
    overdue: 1,
    delivered: 1,
  });
});

test("an empty list (e.g. zero permitted commitments) summarizes to all zeros, not an error", () => {
  assert.deepEqual(getAccountSummary([]), { total: 0, open: 0, unsupported: 0, atRisk: 0, overdue: 0, delivered: 0 });
});
