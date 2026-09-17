// Deliberately not in primary navigation (see AppShell). The backend
// computes a permission-safe retrieval/generation trace for every /search
// and /answer call, but only ever returns it inline with that response —
// nothing is persisted, so there is no standalone audit history for this
// page to show. This is an honest placeholder, not a fabricated feature.
export default function AuditPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">Query observability</p>
      <h1 className="text-3xl font-semibold tracking-[-0.04em] text-zinc-950">Not yet a product feature.</h1>
      <p className="text-sm leading-6 text-zinc-600">
        Every search and answer already carries a permission-safe trace in its response, but nothing is persisted
        server-side, so there is no history to browse independently of the request that produced it. Turning that
        into a real trace-inspection UI is a deliberate future decision, not something this page fabricates in the
        meantime.
      </p>
    </div>
  );
}
