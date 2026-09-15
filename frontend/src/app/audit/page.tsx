import { AuditTracePanel } from "@/features/audit/components/AuditTracePanel";
import { currentUser, evidence } from "@/data/mockData";
import { filterPermittedEvidence } from "@/lib/permissions";
import type { AuditStage } from "@/types/domain";

export default function AuditPage() {
  const acmeEvidence = evidence.filter((item) => item.accountId === "acme-corp");
  const permitted = filterPermittedEvidence(acmeEvidence, currentUser);

  const stages: AuditStage[] = [
    {
      label: "Identity resolved",
      detail: `${currentUser.name} · ${currentUser.role}. Principals: ${currentUser.groups.join(", ")}.`,
      state: "pass",
    },
    {
      label: "ACL filter applied",
      detail: "Resource-level user/group ACLs are evaluated before any mock downstream stage. Only permitted evidence IDs continue.",
      count: permitted.length,
      state: "pass",
    },
    {
      label: "Hybrid retrieval",
      detail: "Future stage: keyword + vector search must execute against the already constrained corpus. No search backend is implemented in V1.",
      state: "info",
    },
    {
      label: "Rerank",
      detail: "Future reranker receives permitted candidates only. A forbidden chunk must never be sent to this stage.",
      state: "info",
    },
    {
      label: "Generation context",
      detail: "The mock search helper builds an answer from permitted evidence. A real LLM call is intentionally deferred.",
      count: permitted.length,
      state: "pass",
    },
    {
      label: "Citation check",
      detail: "Only evidence visible to the requesting user can appear as a citation. Confidential evidence is labeled when it is permitted.",
      state: "pass",
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <section>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Query observability</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-zinc-950">Trace the permission boundary.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">The trace records stages and safe metadata, not a shadow copy of confidential source text. Retrieval, reranking, and LLM stages are architectural placeholders until the backend exists.</p>
      </section>
      <AuditTracePanel stages={stages} />
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm leading-6 text-rose-950">
        <p className="font-semibold">Security invariant</p>
        <p className="mt-1">Unauthorized chunks retrieved = 0 · reranked = 0 · sent to model = 0 · facts emitted = 0.</p>
      </div>
    </div>
  );
}
