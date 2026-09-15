import type { Account, Commitment, Evidence, UserContext } from "../types/domain.ts";

export const accounts: Account[] = [
  {
    id: "acme-corp",
    name: "Acme Corp",
    arr: 420000,
    renewalDate: "2026-11-25",
    owner: "Maya Patel",
    segment: "Enterprise",
  },
  {
    id: "northstar-labs",
    name: "Northstar Labs",
    arr: 185000,
    renewalDate: "2027-01-18",
    owner: "Andre Kim",
    segment: "Mid-market",
  },
];

export const users: Record<string, UserContext> = {
  "account-manager": {
    id: "u-am-1",
    name: "Maya Patel",
    role: "Account Manager",
    groups: ["sales", "account-team-acme"],
  },
  "product-manager": {
    id: "u-pm-1",
    name: "Lena Ortiz",
    role: "Product Manager",
    groups: ["product", "account-team-acme"],
  },
  "vp-product": {
    id: "u-vp-1",
    name: "Victor Chen",
    role: "VP Product",
    groups: ["product", "exec", "account-team-acme"],
  },
};

export const currentUser = users["product-manager"];

export const evidence: Evidence[] = [
  {
    id: "ev-call-sso",
    source: "call",
    accountId: "acme-corp",
    title: "Acme weekly call · Aug 12",
    excerpt: "We'll have SSO ready for you by November 15.",
    department: "sales",
    timestamp: "2026-08-12T14:30:00Z",
    sensitivity: "customer_shared",
    allowedUsers: [],
    allowedGroups: ["sales", "product", "account-team-acme"],
  },
  {
    id: "ev-jira-sso",
    source: "jira",
    accountId: "acme-corp",
    title: "PROJ-481 · Enterprise SSO",
    excerpt: "Target: Q4. Status: under review. No committed release date.",
    department: "product",
    timestamp: "2026-08-13T10:00:00Z",
    sensitivity: "internal",
    allowedUsers: [],
    allowedGroups: ["product", "account-team-acme"],
  },
  {
    id: "ev-slack-sso",
    source: "slack",
    accountId: "acme-corp",
    title: "#product-enterprise · Aug 14",
    excerpt: "November is exploratory; do not commit externally until scope is approved.",
    department: "product",
    timestamp: "2026-08-14T09:12:00Z",
    sensitivity: "confidential",
    allowedUsers: [],
    allowedGroups: ["product", "exec"],
  },
  {
    id: "ev-support-security",
    source: "support",
    accountId: "acme-corp",
    title: "Ticket #4821 · Security questionnaire",
    excerpt: "Customer needs the completed questionnaire before security review can proceed.",
    department: "support",
    timestamp: "2026-09-10T16:45:00Z",
    sensitivity: "internal",
    allowedUsers: [],
    allowedGroups: ["support", "account-team-acme", "product"],
  },
  {
    id: "ev-contract-migration",
    source: "contract",
    accountId: "acme-corp",
    title: "Implementation SOW · Migration support",
    excerpt: "Vendor will provide two assisted migration sessions during onboarding.",
    department: "legal",
    timestamp: "2026-04-03T11:00:00Z",
    sensitivity: "internal",
    allowedUsers: [],
    allowedGroups: ["legal", "sales", "account-team-acme", "product"],
  },
  {
    id: "ev-call-api",
    source: "call",
    accountId: "northstar-labs",
    title: "Northstar roadmap review",
    excerpt: "Bulk export remains a target rather than a committed date.",
    department: "sales",
    timestamp: "2026-09-01T12:00:00Z",
    sensitivity: "customer_shared",
    allowedUsers: [],
    allowedGroups: ["sales", "product"],
  },
];

export const commitments: Commitment[] = [
  {
    id: "com-sso",
    accountId: "acme-corp",
    statement: "Enterprise SSO by November 15",
    promisedBy: "Sarah Chen · Account Executive",
    promiseDate: "2026-08-12",
    deliveryDate: "2026-11-15",
    authority: "sales_unapproved",
    status: "at_risk",
    evidenceIds: ["ev-call-sso", "ev-jira-sso"],
    conflictingEvidenceIds: ["ev-slack-sso"],
  },
  {
    id: "com-security",
    accountId: "acme-corp",
    statement: "Complete security questionnaire",
    promisedBy: "Maya Patel · Account Manager",
    promiseDate: "2026-09-05",
    deliveryDate: "2026-09-12",
    authority: "product_approved",
    status: "overdue",
    evidenceIds: ["ev-support-security"],
    conflictingEvidenceIds: [],
  },
  {
    id: "com-migration",
    accountId: "acme-corp",
    statement: "Two assisted migration sessions",
    promisedBy: "Implementation SOW",
    promiseDate: "2026-04-03",
    deliveryDate: "2026-06-20",
    authority: "contractual",
    status: "delivered",
    evidenceIds: ["ev-contract-migration"],
    conflictingEvidenceIds: [],
  },
  {
    id: "com-bulk-export",
    accountId: "northstar-labs",
    statement: "Bulk export workflow",
    promisedBy: "Roadmap discussion",
    promiseDate: "2026-09-01",
    authority: "product_target",
    status: "on_track",
    evidenceIds: ["ev-call-api"],
    conflictingEvidenceIds: [],
  },
];

export function getAccount(accountId: string): Account | undefined {
  return accounts.find((account) => account.id === accountId);
}

export function getUser(slug: string | undefined): UserContext {
  if (!slug) return currentUser;
  return users[slug] ?? currentUser;
}
