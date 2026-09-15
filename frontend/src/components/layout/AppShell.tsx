import Link from "next/link";
import type { ReactNode } from "react";
import { currentUser } from "@/data/mockData";

const nav = [
  { href: "/", label: "Overview" },
  { href: "/accounts/acme-corp", label: "Accounts" },
  { href: "/search", label: "Ask" },
  { href: "/audit", label: "Audit" },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="sticky top-0 z-20 border-b border-zinc-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-4">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-950 text-sm font-bold text-white">CI</span>
              <span className="hidden sm:block">Commitment Intelligence</span>
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {nav.map((item) => (
                <Link key={item.href} href={item.href} className="rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-950">
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
            <div className="hidden text-right sm:block">
              <p className="text-xs font-semibold text-zinc-900">{currentUser.name}</p>
              <p className="text-[11px] text-zinc-500">{currentUser.role}</p>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8 sm:py-10">{children}</main>
    </div>
  );
}
