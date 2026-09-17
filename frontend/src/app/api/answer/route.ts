import { NextResponse } from "next/server";
import { backendFetch } from "@/lib/api/backend";
import { resolveServerUser } from "@/lib/api/session";
import { parseAnswerRequest } from "@/lib/api/validation";
import { mapCitation } from "@/lib/mapping";
import type { AnswerResponseDTO } from "@/lib/api/dto";

export async function POST(request: Request): Promise<NextResponse> {
  // Identity comes ONLY from the server-resolved, registry-verified
  // session cookie — never from anything in the request body below.
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

  const payload = parseAnswerRequest(raw);
  if (!payload) {
    return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  }

  const backendRes = await backendFetch("/answer", {
    method: "POST",
    userId: user.id,
    body: JSON.stringify(payload),
  });

  if (backendRes.status === 404) {
    return NextResponse.json({ status: "not_found" }, { status: 404 });
  }
  if (!backendRes.ok) {
    // Covers the generation-failure 502 and any other backend/network
    // failure alike: an operational error, never reworded into
    // "insufficient_evidence" — those are different claims.
    return NextResponse.json({ status: "operational_error" }, { status: 502 });
  }

  const dto = (await backendRes.json()) as AnswerResponseDTO;
  // Trimmed on the way out: the answer + mapped citations only. The
  // backend's retrieval/generation trace is deliberately not forwarded —
  // Milestone 7 does not turn it into a product feature (see
  // docs/architecture.md).
  return NextResponse.json({
    answer: dto.answer,
    status: dto.status,
    citations: dto.citations.map(mapCitation),
  });
}
