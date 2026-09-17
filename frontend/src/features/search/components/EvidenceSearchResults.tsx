import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/format";
import type { RetrievalHitView } from "@/types/domain";

const sourceLabels: Record<string, string> = {
  call: "Call transcript",
  support: "Support ticket",
  jira: "Jira",
  slack: "Slack",
  contract: "Contract",
  crm: "CRM",
};

// Renders POST /search results in the backend's own hybrid-ranked order —
// no client-side reranking or filtering. Deliberately does not surface
// lexical_rank/vector_rank/hybrid_score: the API contains them, but this
// page has no product reason to turn retrieval-ranking internals into a
// visible feature (see CLAUDE.md's Milestone 7 notes).
export function EvidenceSearchResults({ hits }: { hits: RetrievalHitView[] }) {
  if (hits.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500">
        No permitted evidence matched this query.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {hits.map((hit) => (
        <article key={hit.chunkId} className="rounded-xl border border-zinc-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{sourceLabels[hit.source] ?? hit.source}</Badge>
            <span className="ml-auto text-xs text-zinc-500">{formatDate(hit.occurredAt)}</span>
          </div>
          <h4 className="mt-3 text-sm font-semibold text-zinc-950">{hit.title}</h4>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{hit.content}</p>
        </article>
      ))}
    </div>
  );
}
