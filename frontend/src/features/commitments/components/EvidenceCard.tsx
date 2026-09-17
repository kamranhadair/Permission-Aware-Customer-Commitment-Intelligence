import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/format";
import type { EvidenceView } from "@/types/domain";

const sourceLabels: Record<EvidenceView["source"], string> = {
  call: "Call transcript",
  support: "Support ticket",
  jira: "Jira",
  slack: "Slack",
  contract: "Contract",
  crm: "CRM",
};

// Renders only source/title/occurred_at/content — the backend's ChunkOut
// also carries `sensitivity`, but that's internal classification metadata,
// not a product decision the account page needs to make from it (see
// docs/architecture.md's Milestone 7 notes). No allowedUsers/allowedGroups/
// ACL field exists on EvidenceView at all — there is nothing here to
// accidentally render.
export function EvidenceCard({ evidence }: { evidence: EvidenceView }) {
  return (
    <article className="rounded-xl border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="info">{sourceLabels[evidence.source] ?? evidence.source}</Badge>
        <span className="ml-auto text-xs text-zinc-500">{formatDate(evidence.occurredAt)}</span>
      </div>
      <h4 className="mt-3 text-sm font-semibold text-zinc-950">{evidence.title}</h4>
      <p className="mt-2 text-sm leading-6 text-zinc-600">&ldquo;{evidence.excerpt}&rdquo;</p>
    </article>
  );
}
