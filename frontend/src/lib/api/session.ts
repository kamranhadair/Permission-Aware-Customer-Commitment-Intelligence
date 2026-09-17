import "server-only";

import { cookies } from "next/headers";
import { backendFetch } from "./backend.ts";
import { resolveIdentity, type ResolvedDemoUser } from "./identity.ts";
import type { DemoUserDTO } from "./dto.ts";

export const DEMO_USER_COOKIE = "demo_user_id";

export type { ResolvedDemoUser };

// GET /dev/demo-users itself needs no identity — it's what lets identity
// be resolved in the first place. Returns [] whenever the demo endpoint
// isn't reachable/mounted, which callers treat the same as "no demo users
// registered" (fail closed, never throw and crash a page over this).
export async function fetchDemoRegistry(): Promise<DemoUserDTO[]> {
  const res = await backendFetch("/dev/demo-users");
  if (!res.ok) return [];
  return (await res.json()) as DemoUserDTO[];
}

// See lib/api/identity.ts for the actual (pure, unit-tested) verification
// logic — this just plugs in the real cookie store and the real registry
// fetch.
export async function resolveServerUser(): Promise<ResolvedDemoUser | null> {
  const store = await cookies();
  const raw = store.get(DEMO_USER_COOKIE)?.value;
  if (!raw) return null;

  const registry = await fetchDemoRegistry();
  return resolveIdentity(raw, registry);
}
