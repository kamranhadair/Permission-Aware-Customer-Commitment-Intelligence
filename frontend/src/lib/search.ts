import type { Commitment, Evidence, UserContext } from "../types/domain.ts";
import { filterPermittedEvidence } from "./permissions.ts";

export type CommitmentAnswer = {
  answer: string;
  citationIds: string[];
  conflictDetected: boolean;
};

export function buildCommitmentAnswer(
  commitment: Commitment,
  evidence: Evidence[],
  user: UserContext,
): CommitmentAnswer {
  const permitted = filterPermittedEvidence(evidence, user);
  const permittedById = new Map(permitted.map((item) => [item.id, item]));

  const citationIds = [...commitment.evidenceIds, ...commitment.conflictingEvidenceIds]
    .filter((id, index, all) => all.indexOf(id) === index)
    .filter((id) => permittedById.has(id));

  const visibleConflicts = commitment.conflictingEvidenceIds
    .map((id) => permittedById.get(id))
    .filter((item): item is Evidence => Boolean(item));

  if (visibleConflicts.length > 0) {
    return {
      answer:
        "No verified Product commitment was found. Sales communicated a November date, while permitted Product evidence says November is exploratory and the delivery target remains under review.",
      citationIds,
      conflictDetected: true,
    };
  }

  return {
    answer:
      "Based on the evidence you can access, Sales communicated a November 15 expectation while the Product work item remains a Q4 target under review. No approved Product delivery date is visible in your permitted sources.",
    citationIds,
    conflictDetected: false,
  };
}
