import { notFound } from "next/navigation";
import { AccountOverview } from "@/features/accounts/components/AccountOverview";
import { AskAccountPanel } from "@/features/commitments/components/AskAccountPanel";
import { CommitmentCard } from "@/features/commitments/components/CommitmentCard";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { getAccount, getCommitments } from "@/lib/api/serverClient";
import { resolveServerUser } from "@/lib/api/session";
import { getAccountSummary } from "@/lib/dashboard";

export default async function AccountPage({ params }: { params: Promise<{ accountId: string }> }) {
  const { accountId } = await params;

  const [accountResult, commitmentsResult, currentUser] = await Promise.all([
    getAccount(accountId),
    getCommitments(accountId),
    resolveServerUser(),
  ]);

  if (accountResult.status === "unresolved" || commitmentsResult.status === "unresolved") {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-600">
        Choose a demo persona above to view this account.
      </div>
    );
  }

  // The backend's nonexistent/cross-org/zero-permitted-document cases are
  // indistinguishable by design — both are handled by the same neutral
  // Next.js not-found state, never a "you don't have permission" message.
  if (accountResult.status === "not_found" || commitmentsResult.status === "not_found") {
    notFound();
  }

  if (accountResult.status === "error" || commitmentsResult.status === "error") {
    return <p className="text-sm text-rose-700">Account data is temporarily unavailable.</p>;
  }

  const account = accountResult.data;
  const commitments = commitmentsResult.data;
  const summary = getAccountSummary(commitments);

  return (
    <div className="space-y-10">
      <AccountOverview account={account} summary={summary} />

      <AskAccountPanel key={`${account.id}:${currentUser?.id ?? "anon"}`} accountSlug={account.id} />

      <section>
        <SectionHeading eyebrow="Customer promise ledger" title="Commitments and authority" />
        <div className="mt-5 space-y-4">
          {commitments.length === 0 ? (
            <p className="text-sm text-zinc-500">No permitted commitments for this account.</p>
          ) : (
            commitments.map((item) => <CommitmentCard key={item.id} commitment={item} />)
          )}
        </div>
      </section>
    </div>
  );
}
