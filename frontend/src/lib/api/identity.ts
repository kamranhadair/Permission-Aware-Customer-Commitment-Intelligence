// The trusted identity boundary's pure core — deliberately free of any
// "server-only"/"next/headers" import so it's directly unit-testable under
// plain Node (see tests/session.test.ts), not just inside a real Next.js
// request context. src/lib/api/session.ts is the thin wrapper that plugs
// in the real cookie store and the real demo-user registry fetch.
//
// A cookie's mere presence is NOT enough — an HttpOnly cookie stops
// ordinary browser JavaScript from reading/writing it, but it does not
// stop an arbitrary HTTP client from sending `Cookie: demo_user_id=
// <anything>`. The raw value is always re-verified against the live
// demo-user registry before it is ever treated as a usable backend
// identity; a value that is missing, malformed, or simply not present in
// the current registry (e.g. stale after a reseed) resolves to `null` —
// an unresolved session — never a guessed/forced identity.

import type { DemoUserDTO } from "./dto.ts";

export type ResolvedDemoUser = {
  id: number;
  name: string;
  label: string | null;
};

export function resolveIdentity(rawCookieValue: string | undefined, registry: DemoUserDTO[]): ResolvedDemoUser | null {
  if (!rawCookieValue) return null;

  const candidateId = Number(rawCookieValue);
  if (!Number.isInteger(candidateId)) return null;

  const match = registry.find((user) => user.id === candidateId);
  if (!match) return null;

  return { id: match.id, name: match.name, label: match.label };
}
