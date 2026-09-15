import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/ui/MetricCard";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CommitmentCard } from "@/features/commitments/components/CommitmentCard";
import { accounts, commitments, currentUser, evidence } from "@/data/mockData";
import { getAccountSummary } from "@/lib/dashboard";
import { filterPermittedEvidence } from "@/lib/permissions";

export default function DashboardPage() {
  const acme = accounts[0];
  const acmeCommitments = commitments.filter((item) => item.accountId === acme.id);
  const summary = getAccountSummary(acme.id, commitments);
  const visibleEvidence = filterPermittedEvidence(evidence.filter((item) => item.accountId === acme.id), currentUser);

  return (
    <div className="space-y-10">
      <section className="overflow-hidden rounded-3xl border border-zinc-200 bg-zinc-950 p-7 text-white shadow-xl sm:p-9">
        <div className="max-w-3xl">
          <Badge tone="neutral">Prototype · frontend only</Badge>
          <h1 className="mt-6 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">Know what was promised before the customer reminds you.</h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-zinc-300">
            Reconstruct customer commitments across calls, tickets, product work, and internal evidence — while keeping unauthorized context out of the answer path.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/search" className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100">Ask about Acme</Link>
            <Link href="/audit" className="rounded-xl border border-zinc-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-zinc-900">Inspect query trace</Link>
          </div>
        </div>
      </section>

      <section>
        <SectionHeading eyebrow="Acme Corp" title="Commitment pulse" action={<Link href="/accounts/acme-corp" className="text-sm font-semibold text-zinc-700 hover:text-zinc-950">Open account →</Link>} />
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Open" value={summary.open} hint={`${summary.total} total commitments`} />
          <MetricCard label="Unsupported" value={summary.unsupported} hint="Promise lacks approval" />
          <MetricCard label="At risk" value={summary.atRisk} hint="Expectation may slip" />
          <MetricCard label="Overdue" value={summary.overdue} hint={`${summary.delivered} delivered`} />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section>
          <SectionHeading eyebrow="Commitment ledger" title="What needs attention" />
          <div className="mt-5 space-y-4">
            {acmeCommitments.map((item) => <CommitmentCard key={item.id} commitment={item} visibleEvidence={visibleEvidence} />)}
          </div>
        </section>

        <aside className="space-y-4">
          <SectionHeading eyebrow="Permission context" title="Current retrieval scope" />
          <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-semibold text-zinc-950">{currentUser.name}</p>
            <p className="mt-1 text-sm text-zinc-500">{currentUser.role}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {currentUser.groups.map((group) => <Badge key={group} tone="neutral">{group}</Badge>)}
            </div>
            <div className="mt-5 border-t border-zinc-100 pt-4">
              <p className="text-3xl font-semibold tracking-tight text-zinc-950">{visibleEvidence.length}</p>
              <p className="mt-1 text-sm text-zinc-500">Acme evidence items permitted before downstream use</p>
            </div>
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
            <p className="font-semibold">The rule that matters</p>
            <p className="mt-2">Forbidden evidence should never enter retrieval candidates, reranking, or the model context.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
