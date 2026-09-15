import type { ReactNode } from "react";

export function SectionHeading({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-500">{eyebrow}</p> : null}
        <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">{title}</h2>
      </div>
      {action}
    </div>
  );
}
