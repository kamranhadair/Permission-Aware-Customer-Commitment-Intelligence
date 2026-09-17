import test from "node:test";
import assert from "node:assert/strict";
import { resolveIdentity } from "../src/lib/api/identity.ts";
import type { DemoUserDTO } from "../src/lib/api/dto.ts";

const registry: DemoUserDTO[] = [
  { id: 210, name: "Maya Chen", email: "maya@demo.example", label: "Account Manager" },
  { id: 211, name: "Lena Ortiz", email: "lena@demo.example", label: "Product Manager" },
];

test("a cookie value matching the current registry resolves to that user", () => {
  assert.deepEqual(resolveIdentity("210", registry), { id: 210, name: "Maya Chen", label: "Account Manager" });
});

test("switching the cookie value resolves to the newly selected user, not a cached one", () => {
  const first = resolveIdentity("210", registry);
  const second = resolveIdentity("211", registry);
  assert.equal(first?.id, 210);
  assert.equal(second?.id, 211);
});

test("a missing cookie is unresolved", () => {
  assert.equal(resolveIdentity(undefined, registry), null);
});

test("a malformed (non-numeric) cookie value is unresolved, never coerced", () => {
  assert.equal(resolveIdentity("999; DROP TABLE users", registry), null);
  assert.equal(resolveIdentity("not-a-number", registry), null);
});

test("a numeric id not present in the current registry is unresolved — an arbitrary DB id is not an accepted demo identity", () => {
  assert.equal(resolveIdentity("999", registry), null);
});

test("a cookie left over from before a reseed (stale id) is unresolved once the registry no longer contains it", () => {
  const staleRegistry: DemoUserDTO[] = [{ id: 300, name: "New Persona", email: "new@demo.example", label: null }];
  assert.equal(resolveIdentity("210", staleRegistry), null);
});

test("an empty registry (demo not seeded) never resolves any cookie value", () => {
  assert.equal(resolveIdentity("210", []), null);
});
