// Pure request-body validators for the browser-facing Route Handlers
// (src/app/api/answer/route.ts). Kept framework-free and exported
// separately so the identity-boundary property they exist to guarantee —
// a body carrying extra authority-like fields (user_id, role, groups,
// org_id, allowed_users, ...) is structurally rejected, never silently
// forwarded — is directly unit-testable without a Next.js request context.

export type AnswerRequestBody = { query: string; account_slug: string };

export function parseAnswerRequest(body: unknown): AnswerRequestBody | null {
  if (typeof body !== "object" || body === null) return null;

  const keys = Object.keys(body);
  if (keys.length !== 2 || !keys.includes("query") || !keys.includes("account_slug")) return null;

  const { query, account_slug: accountSlug } = body as Record<string, unknown>;
  if (typeof query !== "string" || query.trim() === "") return null;
  if (typeof accountSlug !== "string" || accountSlug.trim() === "") return null;

  return { query, account_slug: accountSlug };
}
