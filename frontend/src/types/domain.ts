export type EvidenceSource = "call" | "support" | "jira" | "slack" | "contract" | "crm";
export type Sensitivity = "internal" | "confidential" | "customer_shared";
export type CommitmentAuthority =
  | "customer_expectation"
  | "sales_unapproved"
  | "product_target"
  | "product_approved"
  | "contractual";
export type CommitmentStatus = "on_track" | "at_risk" | "overdue" | "delivered";
export type RiskLevel = "low" | "medium" | "high";

export type Account = {
  id: string;
  name: string;
  arr: number;
  renewalDate: string;
  owner: string;
  segment: string;
};

export type UserContext = {
  id: string;
  name: string;
  role: string;
  groups: string[];
};

export type Evidence = {
  id: string;
  source: EvidenceSource;
  accountId: string;
  title: string;
  excerpt: string;
  department: string;
  timestamp: string;
  sensitivity: Sensitivity;
  allowedUsers: string[];
  allowedGroups: string[];
};

export type Commitment = {
  id: string;
  accountId: string;
  statement: string;
  promisedBy: string;
  promiseDate: string;
  deliveryDate?: string;
  authority: CommitmentAuthority;
  status: CommitmentStatus;
  evidenceIds: string[];
  conflictingEvidenceIds: string[];
};

export type AccountSummary = {
  total: number;
  open: number;
  unsupported: number;
  atRisk: number;
  overdue: number;
  delivered: number;
};

export type AuditStage = {
  label: string;
  detail: string;
  count?: number;
  state: "pass" | "info" | "warning";
};
