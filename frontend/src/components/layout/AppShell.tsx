import Link from "next/link";
import type { ReactNode } from "react";
import { UserSwitcher } from "@/components/ui/UserSwitcher";
import { listDemoUsers } from "@/lib/api/serverClient";
import { resolveServerUser } from "@/lib/api/session";

const nav = [
  { href: "/", label: "Accounts" },
  { href: "/search", label: "Search" },
];

// Async Server Component: resolves the current demo session and the
// demo-user registry server-side, on every request (no client cache),
// so the header always reflects who the server currently believes is
// asking — never a value read out of browser-writable state. /audit is
// deliberately not in primary navigation (see src/app/audit/page.tsx).
export async function AppShell({ children }: { children: ReactNode }) {
  const [demoUsers, currentUser] = await Promise.all([listDemoUsers(), resolveServerUser()]);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="sticky top-0 z-20 border-b border-zinc-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
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
          <div className="flex items-center gap-3">
            {currentUser ? (
              <div className="hidden text-right sm:block">
                <p className="text-xs font-semibold text-zinc-900">{currentUser.name}</p>
                {currentUser.label ? <p className="text-[11px] text-zinc-500">{currentUser.label}</p> : null}
              </div>
            ) : (
              <p className="hidden text-xs text-zinc-500 sm:block">No persona selected</p>
            )}
            <UserSwitcher demoUsers={demoUsers} currentUserId={currentUser?.id ?? null} />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8 sm:py-10">{children}</main>
    </div>
  );
}
