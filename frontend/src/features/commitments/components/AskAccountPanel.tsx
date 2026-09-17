"use client";

import { useReducer, useRef, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/Badge";
import { EvidenceCard } from "@/features/commitments/components/EvidenceCard";
import { askReducer, initialAskState, type AskResolution } from "@/features/commitments/lib/askReducer";
import type { CitationView } from "@/types/domain";

type AnswerApiResponse = { status: "answered" | "insufficient_evidence"; answer: string; citations: CitationView[] };

// The account-page grounded-answer surface. Talks only to same-origin
// POST /api/answer — never to FastAPI directly, and never constructs an
// X-User-Id itself (the Route Handler derives it from the server session
// cookie). The request body sent from here is only {query, account_slug}.
//
// Parent components key this component by `${accountSlug}:${personaId}`
// (a demo persona's numeric id used purely as a React identity key, never
// to authorize anything client-side) so a persona/account switch unmounts
// and remounts it fresh rather than reusing stale local state.
export function AskAccountPanel({ accountSlug }: { accountSlug: string }) {
  const [state, dispatch] = useReducer(askReducer, initialAskState);
  const [question, setQuestion] = useState("");
  const nextRequestId = useRef(0);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;

    const requestId = ++nextRequestId.current;
    dispatch({ type: "SUBMIT", requestId });

    let result: AskResolution;
    try {
      const res = await fetch("/api/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, account_slug: accountSlug }),
      });

      if (res.status === 404) {
        result = { kind: "not_found" };
      } else if (!res.ok) {
        // 401 (no resolved session), 400 (malformed), 502 (generation
        // failure) all surface as one operational state here — none of
        // them mean "no evidence exists", which is a different claim.
        result = { kind: "operational_error" };
      } else {
        const body = (await res.json()) as AnswerApiResponse;
        result =
          body.status === "answered"
            ? { kind: "answered", answer: body.answer, citations: body.citations }
            : { kind: "insufficient_evidence" };
      }
    } catch {
      result = { kind: "operational_error" };
    }

    dispatch({ type: "RESOLVED", requestId, result });
  }

  const isLoading = state.phase === "loading";

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Ask about this account</p>
      <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-3 sm:flex-row">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Has Product committed to November?"
          className="min-w-0 flex-1 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none transition focus:border-zinc-400 focus:bg-white"
        />
        <button
          type="submit"
          disabled={isLoading}
          className="rounded-xl bg-zinc-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:opacity-50"
        >
          {isLoading ? "Asking…" : "Ask"}
        </button>
      </form>

      {isLoading ? <p className="mt-4 text-sm text-zinc-500">Generating a grounded answer…</p> : null}

      {state.phase === "answered" ? (
        <div className="mt-5">
          <Badge tone="success">Grounded answer</Badge>
          <p className="mt-3 text-lg font-medium leading-8 tracking-tight text-zinc-950">{state.answer}</p>
          {state.citations.length > 0 ? (
            <>
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Evidence</p>
              <div className="mt-2 grid gap-3 lg:grid-cols-2">
                {state.citations.map((citation) => (
                  <div key={citation.id}>
                    <p className="mb-1 text-xs font-semibold text-zinc-500">{citation.citationLabel}</p>
                    <EvidenceCard evidence={citation} />
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      ) : null}

      {state.phase === "insufficient_evidence" ? (
        <div className="mt-5 rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
          No permitted evidence answers this question yet.
        </div>
      ) : null}

      {state.phase === "not_found" ? (
        <div className="mt-5 rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
          Account not found or unavailable.
        </div>
      ) : null}

      {state.phase === "operational_error" ? (
        <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-950">
          Answer generation is temporarily unavailable.
        </div>
      ) : null}
    </section>
  );
}
