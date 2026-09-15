# Sample Data Models

These models are intentionally compact. They are enough to support the prototype UI and future backend contracts without pre-designing the entire platform.

## Evidence chunk

```ts
type Evidence = {
  id: string;
  source: "call" | "support" | "jira" | "slack" | "contract" | "crm";
  accountId: string;
  title: string;
  excerpt: string;
  department: string;
  timestamp: string;
  sensitivity: "internal" | "confidential" | "customer_shared";
  allowedUsers: string[];
  allowedGroups: string[];
};
```

## Commitment

```ts
type Commitment = {
  id: string;
  accountId: string;
  statement: string;
  promisedBy: string;
  promiseDate: string;
  deliveryDate?: string;
  authority:
    | "customer_expectation"
    | "sales_unapproved"
    | "product_target"
    | "product_approved"
    | "contractual";
  status: "on_track" | "at_risk" | "overdue" | "delivered";
  evidenceIds: string[];
  conflictingEvidenceIds: string[];
};
```

## User context

```ts
type UserContext = {
  id: string;
  name: string;
  role: string;
  groups: string[];
};
```

Permission filtering should use resource ACLs (`allowedUsers` / `allowedGroups`), not merely `sensitivity` labels.
