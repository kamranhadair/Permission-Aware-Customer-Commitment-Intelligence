import { Badge } from "@/components/ui/Badge";
import { EvidenceCard } from "@/features/commitments/components/EvidenceCard";
import type { Evidence, UserContext } from "@/types/domain";

export function SearchAnswerPanel({
  question,
  answer,
  conflictDetected,
  citations,
  user,
}: {
  question: string;
  answer: string;
  conflictDetected: boolean;
  citations: Evidence[];
  user: UserContext;
}) {
  const hasConfidential = citations.some((item) => item.sensitivity === "confidential");

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="success">Grounded answer</Badge>
        <Badge tone="neutral">{citations.length} citations</Badge>
        {hasConfidential ? <Badge tone="confidential">Includes permitted confidential evidence</Badge> : null}
      </div>
      <p className="mt-5 text-sm font-medium text-zinc-500">{question}</p>
      <p className="mt-3 text-xl font-medium leading-8 tracking-tight text-zinc-950">{answer}</p>
      {conflictDetected ? (
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
          <span className="font-semibold">Conflict detected:</span> the customer-facing promise and permitted Product evidence do not agree.
        </div>
      ) : null}
      <p className="mt-5 border-t border-zinc-100 pt-4 text-xs leading-5 text-zinc-500">
        Answer scope: only evidence authorized for <span className="font-semibold text-zinc-700">{user.name} · {user.role}</span> was assembled into this mock answer.
      </p>
      <div className="mt-6 grid gap-3 lg:grid-cols-2">
        {citations.map((item) => <EvidenceCard key={item.id} evidence={item} />)}
      </div>
    </section>
  );
}
