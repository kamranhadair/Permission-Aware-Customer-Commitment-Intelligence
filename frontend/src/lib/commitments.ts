import type { CommitmentAuthority, CommitmentView, RiskLevel } from "../types/domain.ts";

const AUTHORITY_LABELS: Record<CommitmentAuthority, string> = {
  customer_expectation: "Customer expectation",
  sales_unapproved: "Sales promise · unapproved",
  product_target: "Product target · not committed",
  product_approved: "Product commitment · approved",
  contractual: "Contractual obligation",
};

export function getCommitmentLabel(authority: CommitmentAuthority): string {
  return AUTHORITY_LABELS[authority];
}

// The backend already decides which conflicting evidence (if any) a caller
// may see — a commitment's `conflictingEvidence` array is empty either
// because there truly is none, or because none of it is permitted for this
// user, and those two cases are indistinguishable by design (see
// backend Milestone 2: "an empty conflicting list carries no signal about
// whether unauthorized conflicting evidence exists"). This function reads
// that array directly rather than cross-referencing ids against a
// separately-filtered evidence list, which is no longer necessary once the
// backend hands back already-permitted, already-embedded evidence.
export function getCommitmentRisk(commitment: CommitmentView): RiskLevel {
  const hasVisibleConflict = commitment.conflictingEvidence.length > 0;

  if (commitment.status === "overdue") {
    return "high";
  }

  if (commitment.authority === "sales_unapproved" && (hasVisibleConflict || commitment.status === "at_risk")) {
    return "high";
  }

  if (commitment.status === "at_risk" || hasVisibleConflict || commitment.authority === "product_target") {
    return "medium";
  }

  return "low";
}
