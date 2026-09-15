import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { SearchAnswerPanel } from "@/features/search/components/SearchAnswerPanel";
import { commitments, evidence, getUser } from "@/data/mockData";
import { buildCommitmentAnswer } from "@/lib/search";
import { filterPermittedEvidence } from "@/lib/permissions";

const DEFAULT_QUESTION = "Has Product committed to delivering SSO by November?";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; as?: string }>;
}) {
  const params = await searchParams;
  const user = getUser(params.as);
  const question = params.q?.trim() || DEFAULT_QUESTION;
  const commitment = commitments.find((item) => item.id === "com-sso");
  if (!commitment) return null;

  const result = buildCommitmentAnswer(commitment, evidence, user);
  const permitted = filterPermittedEvidence(evidence, user);
  const citations = result.citationIds
    .map((id) => permitted.find((item) => item.id === id))
    .filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Permission-aware Q&A</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-zinc-950">Ask what was actually promised.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">This prototype assembles the mock answer only after ACL filtering. Switch roles to see the evidence set change.</p>
      </section>

      <form action="/search" className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
        <label htmlFor="q" className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">Question</label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input id="q" name="q" defaultValue={question} className="min-w-0 flex-1 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm outline-none ring-0 transition focus:border-zinc-400 focus:bg-white" />
          <input type="hidden" name="as" value={params.as || "product-manager"} />
          <button className="rounded-xl bg-zinc-950 px-5 py-3 text-sm font-semibold text-white hover:bg-zinc-800">Ask</button>
        </div>
      </form>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-white p-3">
        <span className="mr-1 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">View as</span>
        {[
          ["account-manager", "Account Manager"],
          ["product-manager", "Product Manager"],
          ["vp-product", "VP Product"],
        ].map(([slug, label]) => (
          <Link key={slug} href={`/search?as=${slug}&q=${encodeURIComponent(question)}`}>
            <Badge tone={(params.as || "product-manager") === slug ? "info" : "neutral"}>{label}</Badge>
          </Link>
        ))}
      </div>

      <SearchAnswerPanel question={question} answer={result.answer} conflictDetected={result.conflictDetected} citations={citations} user={user} />
    </div>
  );
}
