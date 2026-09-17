import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/api/backend";
import { resolveServerUser } from "@/lib/api/session";
import { parseSearchRequest } from "@/lib/api/validation";
import { mapRetrievalHit } from "@/lib/mapping";
import type { SearchResponseDTO } from "@/lib/api/dto";

// The narrow, client-facing counterpart to /api/answer, for any future
// interactive (non-full-page-reload) search UI. The current /search page
// is a plain server-rendered GET-form (src/app/search/page.tsx) and calls
// the backend directly via lib/api/serverClient.ts's search() — a Server
// Component is already a trusted server context, so it has no need to
// round-trip through this app's own Route Handler. This endpoint exists
// so a client component gets the same identity/validation boundary
// AskAccountPanel gets, without ever constructing X-User-Id itself.
export async function POST(request: Request): Promise<NextResponse> {
  const user = await resolveServerUser();
  if (!user) {
    return NextResponse.json({ error: "session_required" }, { status: 401 });
  }

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const payload = parseSearchRequest(raw);
  if (!payload) {
    return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  }

  const backendRes = await backendFetch("/search", {
    method: "POST",
    userId: user.id,
    body: JSON.stringify(payload),
  });

  if (backendRes.status === 404) {
    return NextResponse.json({ status: "not_found" }, { status: 404 });
  }
  if (!backendRes.ok) {
    return NextResponse.json({ status: "operational_error" }, { status: 502 });
  }

  const dto = (await backendRes.json()) as SearchResponseDTO;
  // Trace and ranking internals (lexical_rank/vector_rank/hybrid_score)
  // are dropped here too — mapRetrievalHit already strips them.
  return NextResponse.json({ results: dto.results.map(mapRetrievalHit) });
}
