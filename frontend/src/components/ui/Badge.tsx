import type { ReactNode } from "react";

type Tone = "neutral" | "success" | "warning" | "danger" | "confidential" | "info";

const tones: Record<Tone, string> = {
  neutral: "border-zinc-200 bg-zinc-50 text-zinc-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-rose-200 bg-rose-50 text-rose-800",
  confidential: "border-violet-200 bg-violet-50 text-violet-800",
  info: "border-sky-200 bg-sky-50 text-sky-800",
};

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>
      {children}
    </span>
  );
}
