import { setDemoUser } from "@/app/actions";
import type { DemoUserView } from "@/types/domain";

// A plain <form action={serverAction}> works in a Server Component — no
// "use client" needed here. Submitting it invokes setDemoUser (see
// src/app/actions.ts), which is the only place that ever writes the
// identity cookie, and only after checking the submitted id against the
// live demo-user registry. This component never talks to FastAPI itself.
export function UserSwitcher({
  demoUsers,
  currentUserId,
  variant = "compact",
}: {
  demoUsers: DemoUserView[];
  currentUserId: number | null;
  variant?: "compact" | "prompt";
}) {
  if (demoUsers.length === 0) {
    return <p className="text-xs text-zinc-500">No demo personas seeded yet.</p>;
  }

  return (
    <form
      action={setDemoUser}
      className={variant === "compact" ? "flex items-center gap-2" : "flex flex-col items-start gap-3"}
    >
      <select
        name="demoUserId"
        defaultValue={currentUserId ?? ""}
        className="rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-800"
      >
        <option value="" disabled>
          Choose a persona
        </option>
        {demoUsers.map((user) => (
          <option key={user.id} value={user.id}>
            {user.name}
            {user.label ? ` · ${user.label}` : ""}
          </option>
        ))}
      </select>
      <button
        type="submit"
        className="rounded-lg bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-zinc-800"
      >
        Switch
      </button>
    </form>
  );
}
