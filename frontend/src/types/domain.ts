export type EvidenceSource = "call" | "support" | "jira" | "slack" | "contract" | "crm";
export type CommitmentAuthority =
  | "customer_expectation"
  | "sales_unapproved"
  | "product_target"
  | "product_approved"
  | "contractual";
export type CommitmentStatus = "on_track" | "at_risk" | "overdue" | "delivered";
export type RiskLevel = "low" | "medium" | "high";

// View models for real (backend-sourced) data. These are deliberately NOT
// the old mock shapes (frontend/src/data/mockData.ts, retired) — the
// backend's own contracts differ from that prototype shape (no ARR/
// renewal/owner/segment on an account; evidence arrives embedded and
// pre-filtered on a commitment, not as separate evidenceIds arrays to
// resolve; no allowedUsers/allowedGroups ever leave the server). Mapping
// from backend DTOs happens in src/lib/mapping.ts and performs no ACL
// filtering of its own — the backend has already done that.

export type AccountView = {
  id: string; // the backend's account slug
  name: string;
};

export type EvidenceView = {
  id: string;
  source: EvidenceSource;
  title: string;
  excerpt: string;
  occurredAt: string;
};

export type CommitmentView = {
  id: string;
  statement: string;
  promisedBy: string;
  promiseDate: string;
  deliveryDate?: string;
  authority: CommitmentAuthority;
  status: CommitmentStatus;
  supportingEvidence: EvidenceView[];
  conflictingEvidence: EvidenceView[];
};

export type AccountSummary = {
  total: number;
  open: number;
  unsupported: number;
  atRisk: number;
  overdue: number;
  delivered: number;
};

export type CitationView = EvidenceView & {
  // The server's own "E1", "E2", ... citation id. Never a "C*" internal
  // commitment-context id — the backend's citation contract only ever
  // emits evidence citations (see backend generation/validation.py).
  citationLabel: string;
};

export type RetrievalHitView = {
  chunkId: string;
  documentId: string;
  source: EvidenceSource;
  title: string;
  content: string;
  occurredAt: string;
};

// Presentation-safe demo persona, from GET /dev/demo-users. `id` is safe to
// pass to the browser and use as a React key or a form value submitted back
// to the setDemoUser Server Action — it must never be used by the browser
// to construct an X-User-Id header itself (see src/lib/api/session.ts).
export type DemoUserView = {
  id: number;
  name: string;
  email: string;
  label: string | null;
};
