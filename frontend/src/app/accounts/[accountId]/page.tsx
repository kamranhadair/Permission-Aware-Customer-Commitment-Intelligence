import { notFound } from "next/navigation";
import { AccountOverview } from "@/features/accounts/components/AccountOverview";
import { CommitmentCard } from "@/features/commitments/components/CommitmentCard";
import { EvidenceCard } from "@/features/commitments/components/EvidenceCard";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { commitments, currentUser, evidence, getAccount } from "@/data/mockData";
import { getAccountSummary } from "@/lib/dashboard";
import { filterPermittedEvidence } from "@/lib/permissions";

export default async function AccountPage({ params }: { params: Promise<{ accountId: string }> }) {
  const { accountId } = await params;
  const account = getAccount(accountId);
  if (!account) notFound();

  const accountCommitments = commitments.filter((item) => item.accountId === account.id);
  const accountEvidence = evidence.filter((item) => item.accountId === account.id);
  const visibleEvidence = filterPermittedEvidence(accountEvidence, currentUser);
  const summary = getAccountSummary(account.id, commitments);

  return (
    <div className="space-y-10">
      <AccountOverview account={account} summary={summary} />

      <section>
        <SectionHeading eyebrow="Customer promise ledger" title="Commitments and authority" />
        <div className="mt-5 space-y-4">
          {accountCommitments.map((item) => <CommitmentCard key={item.id} commitment={item} visibleEvidence={visibleEvidence} />)}
        </div>
      </section>

      <section>
        <SectionHeading eyebrow="Permitted source material" title={`Evidence visible to ${currentUser.name}`} />
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {visibleEvidence.map((item) => <EvidenceCard key={item.id} evidence={item} />)}
        </div>
      </section>
    </div>
  );
}
