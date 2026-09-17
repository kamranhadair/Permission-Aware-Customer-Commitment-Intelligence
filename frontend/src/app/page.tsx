import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { AccountList } from "@/features/accounts/components/AccountList";
import { listAccounts } from "@/lib/api/serverClient";

export default async function DashboardPage() {
  const result = await listAccounts();

  return (
    <div className="space-y-10">
      <section className="overflow-hidden rounded-3xl border border-zinc-200 bg-zinc-950 p-7 text-white shadow-xl sm:p-9">
        <div className="max-w-3xl">
          <Badge tone="neutral">Permission-aware backend</Badge>
          <h1 className="mt-6 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">Know what was promised before the customer reminds you.</h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-zinc-300">
            Reconstruct customer commitments across calls, tickets, and internal evidence. The backend decides what
            you can see &mdash; this screen only renders what it returned.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/search" className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100">Search evidence</Link>
          </div>
        </div>
      </section>

      <section>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Accounts visible to the current persona</p>
        <div className="mt-5">
          {result.status === "unresolved" ? (
            <p className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500">
              Choose a demo persona above to see accounts.
            </p>
          ) : result.status === "ok" ? (
            <AccountList accounts={result.data} />
          ) : (
            <p className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
              Accounts are temporarily unavailable.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
