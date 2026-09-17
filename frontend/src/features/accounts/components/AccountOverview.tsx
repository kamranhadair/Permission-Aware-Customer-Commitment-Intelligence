import { MetricCard } from "@/components/ui/MetricCard";
import type { AccountSummary, AccountView } from "@/types/domain";

// No ARR/renewal-date/owner/segment card: the backend's Account model has
// no such columns (see CLAUDE.md's Milestone 7 notes) — those were mock-
// only fields from the V1 prototype, and this page only renders what a
// real backend response actually contains rather than fabricating values.
export function AccountOverview({ account, summary }: { account: AccountView; summary: AccountSummary }) {
  return (
    <section>
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Customer account</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-zinc-950">{account.name}</h1>
      </div>
      <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Open commitments" value={summary.open} hint={`${summary.total} total tracked`} />
        <MetricCard label="Unsupported promises" value={summary.unsupported} hint="Needs authority review" />
        <MetricCard label="At risk" value={summary.atRisk} hint="Customer expectation risk" />
        <MetricCard label="Overdue" value={summary.overdue} hint={`${summary.delivered} delivered`} />
      </div>
    </section>
  );
}
