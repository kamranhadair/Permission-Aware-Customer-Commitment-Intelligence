import { MetricCard } from "@/components/ui/MetricCard";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Account, AccountSummary } from "@/types/domain";

export function AccountOverview({ account, summary }: { account: Account; summary: AccountSummary }) {
  return (
    <section>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Customer account</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-zinc-950">{account.name}</h1>
          <p className="mt-3 text-sm text-zinc-500">{account.segment} · Owner {account.owner} · Renewal {formatDate(account.renewalDate)}</p>
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-right shadow-sm">
          <p className="text-xs uppercase tracking-[0.12em] text-zinc-400">ARR</p>
          <p className="mt-1 text-xl font-semibold text-zinc-950">{formatCurrency(account.arr)}</p>
        </div>
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
