import type { AccountSummary, Commitment } from "../types/domain.ts";

export function getAccountSummary(accountId: string, commitments: Commitment[]): AccountSummary {
  const accountCommitments = commitments.filter((item) => item.accountId === accountId);

  return {
    total: accountCommitments.length,
    open: accountCommitments.filter((item) => item.status !== "delivered").length,
    unsupported: accountCommitments.filter((item) => item.authority === "sales_unapproved").length,
    atRisk: accountCommitments.filter((item) => item.status === "at_risk").length,
    overdue: accountCommitments.filter((item) => item.status === "overdue").length,
    delivered: accountCommitments.filter((item) => item.status === "delivered").length,
  };
}
