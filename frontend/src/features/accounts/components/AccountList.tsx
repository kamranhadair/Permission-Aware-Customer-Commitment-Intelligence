import Link from "next/link";
import type { AccountView } from "@/types/domain";

// Renders exactly what GET /accounts returned for the current persona —
// no client-side filtering, no fabricated accounts, no hint of anything
// the backend chose not to include.
export function AccountList({ accounts }: { accounts: AccountView[] }) {
  if (accounts.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500">
        No accounts are visible to this persona.
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {accounts.map((account) => (
        <Link
          key={account.id}
          href={`/accounts/${encodeURIComponent(account.id)}`}
          className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-zinc-400"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Account</p>
          <h3 className="mt-2 text-lg font-semibold text-zinc-950">{account.name}</h3>
        </Link>
      ))}
    </div>
  );
}
