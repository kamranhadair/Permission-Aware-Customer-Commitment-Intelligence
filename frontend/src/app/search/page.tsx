import { EvidenceSearchResults } from "@/features/search/components/EvidenceSearchResults";
import { listAccounts, search } from "@/lib/api/serverClient";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; account?: string }>;
}) {
  const params = await searchParams;
  const query = params.q?.trim() ?? "";
  const accountSlug = params.account?.trim() || undefined;

  const accountsResult = await listAccounts();
  const accounts = accountsResult.status === "ok" ? accountsResult.data : [];

  const searchResult = query.length > 0 ? await search(query, accountSlug) : null;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Permission-aware evidence search</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-zinc-950">Search permitted evidence.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">
          Results come directly from the backend&rsquo;s hybrid retrieval, already scoped to what the current persona
          may see. Nothing here is reranked or filtered in the browser.
        </p>
      </section>

      <form action="/search" className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
        <label htmlFor="q" className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Question</label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input id="q" name="q" defaultValue={query} className="min-w-0 flex-1 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none transition focus:border-zinc-400 focus:bg-white" />
          <select name="account" defaultValue={accountSlug ?? ""} className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm">
            <option value="">All visible accounts</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
          <button className="rounded-xl bg-zinc-950 px-5 py-3 text-sm font-semibold text-white hover:bg-zinc-800">Search</button>
        </div>
      </form>

      {accountsResult.status === "unresolved" ? (
        <p className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500">
          Choose a demo persona above to search.
        </p>
      ) : null}

      {searchResult ? (
        searchResult.status === "ok" ? (
          <EvidenceSearchResults hits={searchResult.data} />
        ) : searchResult.status === "not_found" ? (
          <p className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500">Account not found or unavailable.</p>
        ) : searchResult.status === "unresolved" ? null : (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">Search is temporarily unavailable.</p>
        )
      ) : null}
    </div>
  );
}
