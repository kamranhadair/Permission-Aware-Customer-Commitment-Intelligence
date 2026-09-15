import { Badge } from "@/components/ui/Badge";
import type { AuditStage } from "@/types/domain";

export function AuditTracePanel({ stages }: { stages: AuditStage[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      {stages.map((stage, index) => (
        <div key={stage.label} className="flex gap-4 border-b border-zinc-100 p-5 last:border-b-0">
          <div className="flex flex-col items-center">
            <span className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-200 bg-zinc-50 text-xs font-semibold text-zinc-700">{index + 1}</span>
            {index < stages.length - 1 ? <span className="mt-2 h-full w-px bg-zinc-200" /> : null}
          </div>
          <div className="min-w-0 flex-1 pb-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-zinc-950">{stage.label}</h3>
              <Badge tone={stage.state === "pass" ? "success" : stage.state === "warning" ? "warning" : "neutral"}>
                {stage.state === "pass" ? "Pass" : stage.state === "warning" ? "Review" : "Mock stage"}
              </Badge>
              {typeof stage.count === "number" ? <span className="text-xs text-zinc-400">{stage.count} items</span> : null}
            </div>
            <p className="mt-2 text-sm leading-6 text-zinc-600">{stage.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
