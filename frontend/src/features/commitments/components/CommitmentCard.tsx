import { Badge } from "@/components/ui/Badge";
import { getCommitmentLabel, getCommitmentRisk } from "@/lib/commitments";
import { formatDate } from "@/lib/format";
import type { Commitment, Evidence } from "@/types/domain";

const statusStyle = {
  on_track: { label: "On track", tone: "success" as const },
  at_risk: { label: "At risk", tone: "danger" as const },
  overdue: { label: "Overdue", tone: "danger" as const },
  delivered: { label: "Delivered", tone: "success" as const },
};

export function CommitmentCard({ commitment, visibleEvidence }: { commitment: Commitment; visibleEvidence: Evidence[] }) {
  const status = statusStyle[commitment.status];
  const risk = getCommitmentRisk(commitment, visibleEvidence);
  const visibleIds = new Set(visibleEvidence.map((item) => item.id));
  const visibleConflicts = commitment.conflictingEvidenceIds.filter((id) => visibleIds.has(id));

  return (
    <article className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={status.tone}>{status.label}</Badge>
        <Badge tone={commitment.authority === "sales_unapproved" ? "warning" : "neutral"}>{getCommitmentLabel(commitment.authority)}</Badge>
        {risk === "high" ? <Badge tone="danger">High risk</Badge> : null}
      </div>
      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 className="text-lg font-semibold tracking-tight text-zinc-950">{commitment.statement}</h3>
          <p className="mt-1 text-sm text-zinc-500">Promised by {commitment.promisedBy} · {formatDate(commitment.promiseDate)}</p>
        </div>
        {commitment.deliveryDate ? (
          <div className="shrink-0 text-left lg:text-right">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Delivery</p>
            <p className="mt-1 text-sm font-semibold text-zinc-900">{formatDate(commitment.deliveryDate)}</p>
          </div>
        ) : null}
      </div>
      {visibleConflicts.length > 0 ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-950">
          <span className="font-semibold">Conflict detected.</span> Customer-facing expectation exceeds permitted internal commitment evidence.
        </div>
      ) : null}
    </article>
  );
}
