import test from "node:test";
import assert from "node:assert/strict";
import { buildCommitmentAnswer } from "../src/lib/search.ts";
import type { Commitment, Evidence, UserContext } from "../src/types/domain.ts";

const commitment: Commitment = {
  id: "com-sso",
  accountId: "acme-corp",
  statement: "SSO by November 15",
  promisedBy: "Sarah Chen",
  promiseDate: "2026-08-12",
  deliveryDate: "2026-11-15",
  authority: "sales_unapproved",
  status: "at_risk",
  evidenceIds: ["call", "jira"],
  conflictingEvidenceIds: ["slack"],
};

const evidence: Evidence[] = [
  { id: "call", source: "call", accountId: "acme-corp", title: "Customer call", excerpt: "We will have SSO by November 15.", department: "sales", timestamp: "2026-08-12T14:30:00Z", sensitivity: "customer_shared", allowedUsers: [], allowedGroups: ["account-team-acme"] },
  { id: "jira", source: "jira", accountId: "acme-corp", title: "PROJ-481", excerpt: "Target Q4. Status: under review.", department: "product", timestamp: "2026-08-13T10:00:00Z", sensitivity: "internal", allowedUsers: [], allowedGroups: ["account-team-acme", "product"] },
  { id: "slack", source: "slack", accountId: "acme-corp", title: "Product leadership", excerpt: "November is exploratory; do not commit externally.", department: "product", timestamp: "2026-08-14T09:12:00Z", sensitivity: "confidential", allowedUsers: [], allowedGroups: ["product", "exec"] },
];

const accountManager: UserContext = { id: "am", name: "Maya", role: "Account Manager", groups: ["account-team-acme", "sales"] };
const productManager: UserContext = { id: "pm", name: "Lena", role: "Product Manager", groups: ["account-team-acme", "product"] };

test("answer for account manager excludes confidential product evidence and its facts", () => {
  const result = buildCommitmentAnswer(commitment, evidence, accountManager);
  assert.deepEqual(result.citationIds, ["call", "jira"]);
  assert.equal(result.conflictDetected, false);
  assert.equal(result.answer.includes("exploratory"), false);
});

test("answer for product manager can surface a visible conflict with citation", () => {
  const result = buildCommitmentAnswer(commitment, evidence, productManager);
  assert.deepEqual(result.citationIds, ["call", "jira", "slack"]);
  assert.equal(result.conflictDetected, true);
  assert.equal(result.answer.includes("exploratory"), true);
});
