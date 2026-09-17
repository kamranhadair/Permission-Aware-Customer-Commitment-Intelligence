import type { AccountSummary, CommitmentView } from "../types/domain.ts";

// Takes an already account-scoped commitment list (GET
// /accounts/{slug}/commitments is inherently scoped to one account, unlike
// the old mock's single global array) — no accountId filtering step is
// needed here anymore.
export function getAccountSummary(commitments: CommitmentView[]): AccountSummary {
  return {
    total: commitments.length,
    open: commitments.filter((item) => item.status !== "delivered").length,
    unsupported: commitments.filter((item) => item.authority === "sales_unapproved").length,
    atRisk: commitments.filter((item) => item.status === "at_risk").length,
    overdue: commitments.filter((item) => item.status === "overdue").length,
    delivered: commitments.filter((item) => item.status === "delivered").length,
  };
}
