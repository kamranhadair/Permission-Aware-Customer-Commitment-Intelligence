import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/format";
import type { Evidence } from "@/types/domain";

const sourceLabels: Record<Evidence["source"], string> = {
  call: "Call transcript",
  support: "Support ticket",
  jira: "Jira",
  slack: "Slack",
  contract: "Contract",
  crm: "CRM",
};

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <article className="rounded-xl border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="info">{sourceLabels[evidence.source]}</Badge>
        {evidence.sensitivity === "confidential" ? <Badge tone="confidential">Confidential · permitted</Badge> : null}
        <span className="ml-auto text-xs text-zinc-500">{formatDate(evidence.timestamp)}</span>
      </div>
      <h4 className="mt-3 text-sm font-semibold text-zinc-950">{evidence.title}</h4>
      <p className="mt-2 text-sm leading-6 text-zinc-600">“{evidence.excerpt}”</p>
      <p className="mt-3 text-xs text-zinc-400">Evidence ID · {evidence.id}</p>
    </article>
  );
}
