import "server-only";

// Server-only: BACKEND_URL is never exposed to the browser (no
// NEXT_PUBLIC_ prefix) and this module is never imported from a "use
// client" file — the `server-only` import throws a build error if that
// ever happens by accident.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

type BackendFetchInit = Omit<RequestInit, "cache"> & {
  // Only ever set from a server-resolved, registry-verified identity
  // (see session.ts) — never from a value the browser sent directly.
  userId?: number;
};

export async function backendFetch(path: string, init: BackendFetchInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.userId !== undefined) {
    headers.set("X-User-Id", String(init.userId));
  }
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers,
    // Explicit, not inferred: every call here is authorization-sensitive
    // (its result depends on which demo user is asking), so it must never
    // be shared across requests/users by Next's fetch cache.
    cache: "no-store",
  });
}
