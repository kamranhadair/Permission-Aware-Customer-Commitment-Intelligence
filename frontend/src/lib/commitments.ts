import type { Commitment, CommitmentAuthority, Evidence, RiskLevel } from "../types/domain.ts";

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

export function getCommitmentRisk(commitment: Commitment, evidence: Evidence[]): RiskLevel {
  const availableEvidence = new Set(evidence.map((item) => item.id));
  const hasVisibleConflict = commitment.conflictingEvidenceIds.some((id) => availableEvidence.has(id));

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
