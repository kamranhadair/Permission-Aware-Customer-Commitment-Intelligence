import type { Evidence, UserContext } from "../types/domain.ts";

export function canAccessEvidence(evidence: Evidence, user: UserContext): boolean {
  if (evidence.allowedUsers.includes(user.id)) {
    return true;
  }

  return evidence.allowedGroups.some((group) => user.groups.includes(group));
}

export function filterPermittedEvidence(evidence: Evidence[], user: UserContext): Evidence[] {
  return evidence.filter((item) => canAccessEvidence(item, user));
}
