import "server-only";

import { backendFetch } from "./backend.ts";
import { resolveServerUser } from "./session.ts";
import { mapAccount, mapCommitment, mapDemoUser, mapRetrievalHit } from "../mapping.ts";
import type { AccountDTO, CommitmentDTO, DemoUserDTO, SearchResponseDTO } from "./dto.ts";
import type { AccountView, CommitmentView, DemoUserView, RetrievalHitView } from "../../types/domain.ts";

// Every authorization-sensitive read goes through this module. None of
// these functions take a userId parameter from the caller — identity is
// always derived server-side from the cookie-resolved, registry-verified
// session (see session.ts), never threaded in as a raw value a page could
// get from anywhere else.
export type ApiResult<T> =
  | { status: "ok"; data: T }
  // No valid demo persona is currently selected for this request.
  | { status: "unresolved" }
  // The backend's own indistinguishable 404: nonexistent, cross-org, and
  // same-org-but-no-permitted-document all resolve here identically.
  | { status: "not_found" }
  // Network/5xx — an operational failure, not an authorization outcome.
  | { status: "error" };

export async function listDemoUsers(): Promise<DemoUserView[]> {
  const res = await backendFetch("/dev/demo-users");
  if (!res.ok) return [];
  const dtos = (await res.json()) as DemoUserDTO[];
  return dtos.map(mapDemoUser);
}

export async function listAccounts(): Promise<ApiResult<AccountView[]>> {
  const user = await resolveServerUser();
  if (!user) return { status: "unresolved" };

  const res = await backendFetch("/accounts", { userId: user.id });
  if (res.status === 401) return { status: "unresolved" };
  if (!res.ok) return { status: "error" };

  const dtos = (await res.json()) as AccountDTO[];
  return { status: "ok", data: dtos.map(mapAccount) };
}

export async function getAccount(slug: string): Promise<ApiResult<AccountView>> {
  const user = await resolveServerUser();
  if (!user) return { status: "unresolved" };

  const res = await backendFetch(`/accounts/${encodeURIComponent(slug)}`, { userId: user.id });
  if (res.status === 401) return { status: "unresolved" };
  if (res.status === 404) return { status: "not_found" };
  if (!res.ok) return { status: "error" };

  return { status: "ok", data: mapAccount((await res.json()) as AccountDTO) };
}

export async function getCommitments(slug: string): Promise<ApiResult<CommitmentView[]>> {
  const user = await resolveServerUser();
  if (!user) return { status: "unresolved" };

  const res = await backendFetch(`/accounts/${encodeURIComponent(slug)}/commitments`, { userId: user.id });
  if (res.status === 401) return { status: "unresolved" };
  if (res.status === 404) return { status: "not_found" };
  if (!res.ok) return { status: "error" };

  const dtos = (await res.json()) as CommitmentDTO[];
  return { status: "ok", data: dtos.map(mapCommitment) };
}

// Server-rendered evidence search (the /search page is a plain GET-form
// page, matching the rest of this app's server-rendering pattern — no
// client fetch, so no narrow Route Handler is needed for it, unlike the
// account page's interactive Ask panel; see src/app/api/answer/route.ts).
export async function search(query: string, accountSlug?: string): Promise<ApiResult<RetrievalHitView[]>> {
  const user = await resolveServerUser();
  if (!user) return { status: "unresolved" };

  const res = await backendFetch("/search", {
    method: "POST",
    userId: user.id,
    body: JSON.stringify(accountSlug ? { query, account_slug: accountSlug } : { query }),
  });
  if (res.status === 401) return { status: "unresolved" };
  if (res.status === 404) return { status: "not_found" };
  if (!res.ok) return { status: "error" };

  const dto = (await res.json()) as SearchResponseDTO;
  return { status: "ok", data: dto.results.map(mapRetrievalHit) };
}
