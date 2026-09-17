"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { listDemoUsers } from "@/lib/api/serverClient";
import { DEMO_USER_COOKIE } from "@/lib/api/session";

// The browser may propose a persona (that's the point of the demo), but
// this action is the only place that ever writes the identity cookie, and
// it only does so after checking the submitted id against the current
// demo-user registry. An id that doesn't match anything currently
// registered (unregistered, stale after a reseed, or simply made up) is
// silently rejected — the cookie is left untouched, so the session stays
// exactly as unresolved/resolved as it already was.
export async function setDemoUser(formData: FormData): Promise<void> {
  const raw = formData.get("demoUserId");
  const candidateId = Number(raw);
  if (!Number.isInteger(candidateId)) return;

  const registry = await listDemoUsers();
  const match = registry.find((user) => user.id === candidateId);
  if (!match) return;

  const store = await cookies();
  store.set(DEMO_USER_COOKIE, String(match.id), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });

  // Every server-rendered read is authorization-sensitive and already
  // fetches with cache: "no-store" (see lib/api/backend.ts), so this isn't
  // reviving stale framework-cached data — it forces the whole tree to
  // re-render against the new cookie so the previous persona's rendered
  // output doesn't linger on screen for a moment after the switch.
  revalidatePath("/", "layout");
}
