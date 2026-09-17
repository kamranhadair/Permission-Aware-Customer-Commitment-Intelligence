import test from "node:test";
import assert from "node:assert/strict";
import { parseAnswerRequest, parseSearchRequest } from "../src/lib/api/validation.ts";

test("accepts exactly {query, account_slug}", () => {
  assert.deepEqual(parseAnswerRequest({ query: "Has Product committed to November?", account_slug: "acme-corp" }), {
    query: "Has Product committed to November?",
    account_slug: "acme-corp",
  });
});

test("rejects a body carrying an extra user_id field — never silently forwarded", () => {
  assert.equal(parseAnswerRequest({ query: "q", account_slug: "acme-corp", user_id: 999 }), null);
});

test("rejects a body asserting role/groups/org_id", () => {
  assert.equal(
    parseAnswerRequest({ query: "q", account_slug: "acme-corp", role: "vp", groups: ["exec"], org_id: 1 }),
    null,
  );
});

test("rejects a body asserting allowed_users", () => {
  assert.equal(parseAnswerRequest({ query: "q", account_slug: "acme-corp", allowed_users: [1, 2] }), null);
});

test("rejects a missing account_slug", () => {
  assert.equal(parseAnswerRequest({ query: "q" }), null);
});

test("rejects a missing query", () => {
  assert.equal(parseAnswerRequest({ account_slug: "acme-corp" }), null);
});

test("rejects empty-string fields", () => {
  assert.equal(parseAnswerRequest({ query: "  ", account_slug: "acme-corp" }), null);
  assert.equal(parseAnswerRequest({ query: "q", account_slug: "" }), null);
});

test("rejects non-string field types", () => {
  assert.equal(parseAnswerRequest({ query: 123, account_slug: "acme-corp" }), null);
});

test("rejects non-object bodies", () => {
  assert.equal(parseAnswerRequest("not an object"), null);
  assert.equal(parseAnswerRequest(null), null);
  assert.equal(parseAnswerRequest([1, 2, 3]), null);
});

test("parseSearchRequest accepts query alone (account_slug omitted -> search all visible accounts)", () => {
  assert.deepEqual(parseSearchRequest({ query: "SSO" }), { query: "SSO" });
});

test("parseSearchRequest accepts {query, account_slug}", () => {
  assert.deepEqual(parseSearchRequest({ query: "SSO", account_slug: "acme-corp" }), {
    query: "SSO",
    account_slug: "acme-corp",
  });
});

test("parseSearchRequest rejects a body carrying user_id/role/groups/org_id/allowed_users", () => {
  assert.equal(parseSearchRequest({ query: "SSO", user_id: 999 }), null);
  assert.equal(parseSearchRequest({ query: "SSO", role: "vp" }), null);
  assert.equal(parseSearchRequest({ query: "SSO", groups: ["exec"] }), null);
  assert.equal(parseSearchRequest({ query: "SSO", org_id: 1 }), null);
  assert.equal(parseSearchRequest({ query: "SSO", allowed_users: [1, 2] }), null);
});

test("parseSearchRequest rejects a missing query", () => {
  assert.equal(parseSearchRequest({ account_slug: "acme-corp" }), null);
});

test("parseSearchRequest rejects empty-string fields", () => {
  assert.equal(parseSearchRequest({ query: "  " }), null);
  assert.equal(parseSearchRequest({ query: "SSO", account_slug: "" }), null);
});

test("parseSearchRequest rejects non-object bodies", () => {
  assert.equal(parseSearchRequest("not an object"), null);
  assert.equal(parseSearchRequest(null), null);
});
