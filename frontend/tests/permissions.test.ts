import test from "node:test";
import assert from "node:assert/strict";
import { canAccessEvidence, filterPermittedEvidence } from "../src/lib/permissions.ts";
import type { Evidence, UserContext } from "../src/types/domain.ts";

const user: UserContext = {
  id: "u-am-1",
  name: "Maya Patel",
  role: "Account Manager",
  groups: ["account-team-acme", "sales"],
};

const baseEvidence: Evidence = {
  id: "ev-1",
  source: "call",
  accountId: "acme-corp",
  title: "Customer call",
  excerpt: "We will have SSO by November.",
  department: "sales",
  timestamp: "2026-08-12T14:30:00Z",
  sensitivity: "customer_shared",
  allowedUsers: [],
  allowedGroups: [],
};

test("allows evidence granted directly to the user", () => {
  assert.equal(canAccessEvidence({ ...baseEvidence, allowedUsers: ["u-am-1"] }, user), true);
});

test("allows evidence granted to one of the user's groups", () => {
  assert.equal(canAccessEvidence({ ...baseEvidence, allowedGroups: ["account-team-acme"] }, user), true);
});

test("rejects evidence with no matching user or group ACL", () => {
  assert.equal(canAccessEvidence({ ...baseEvidence, allowedGroups: ["exec"] }, user), false);
});

test("filterPermittedEvidence excludes forbidden chunks before downstream use", () => {
  const visible = { ...baseEvidence, id: "visible", allowedGroups: ["sales"] };
  const forbidden = { ...baseEvidence, id: "forbidden", allowedGroups: ["exec"] };
  assert.deepEqual(filterPermittedEvidence([visible, forbidden], user).map((item) => item.id), ["visible"]);
});
