// One place that turns raw keys from the API (plan features, states, roles, adapters, tools, …)
// into human-readable labels. Unknown keys fall back to sentence case so new values still read well.

const KNOWN: Record<string, string> = {
  // Plan features
  saml_sso: "SAML single sign-on", sso: "Single sign-on", scim: "SCIM provisioning", audit_log_export: "Audit log export",
  dedicated_csm: "Dedicated success manager", dashboards: "Dashboards", reporting: "Reporting", api_access: "API access",
  custom_roles: "Custom roles", priority_support: "Priority support", data_connectors: "Data connectors",
  // Request categories
  access: "Access", billing: "Billing", product_issue: "Product issue", unsupported: "Unsupported", unclassified: "Not classified",
  // Priorities
  low: "Low", normal: "Normal", high: "High", urgent: "Urgent",
  // Ticket statuses
  open: "Open", pending_customer: "Waiting on customer", solved: "Solved", closed: "Closed",
  // Roles
  admin: "Admin", analyst: "Analyst", viewer: "Viewer", owner: "Owner", reviewer: "Reviewer",
  // Adapters
  internal: "Internal tickets", github: "GitHub Issues",
  // Next actions and resolutions
  resolve: "Resolve with reply", clarify: "Ask for clarification", escalate: "Escalate",
  resolved: "Resolved", clarification_requested: "Clarification requested", escalated: "Escalated",
  // Tools
  lookup_customer: "Look up customer", get_subscription: "Get subscription", get_existing_tickets: "Check existing tickets",
  search_knowledge_base: "Search knowledge base", propose_ticket_action: "Propose ticket action",
  // Execution / import statuses
  succeeded: "Succeeded", failed: "Failed", pending: "Pending", processing: "Processing", ready: "Ready",
};

/** Sentence-case fallback: "audit_log_export" → "Audit log export". */
export function humanize(key: string | null | undefined): string {
  if (!key) return "";
  const k = String(key).trim();
  if (KNOWN[k]) return KNOWN[k];
  const lower = k.toLowerCase();
  if (KNOWN[lower]) return KNOWN[lower];
  const words = k.replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Humanize a comma-separated list of keys ("dashboards, saml_sso") when every item looks like a key. */
export function humanizeList(value: string): string {
  const parts = value.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length === 0 || !parts.every((p) => /^[a-z0-9_]+$/.test(p))) return value;
  return parts.map(humanize).join(", ");
}

export const STATE_LABEL: Record<string, string> = {
  received: "Received", classified: "Classified", context_resolved: "Context resolved", retrieved: "Retrieved",
  awaiting_review: "Awaiting review", approved: "Approved", executing: "Executing", completed: "Completed",
  failed: "Execution failed", error: "Error", stale: "Stale evidence", rejected: "Rejected", unsupported: "Unsupported",
};
export const stateLabel = (s: string) => STATE_LABEL[s] ?? humanize(s);

export type Tone = "neutral" | "accent" | "warn" | "danger" | "ok";
export const STATE_TONE: Record<string, Tone> = {
  awaiting_review: "accent", approved: "accent", executing: "accent", completed: "ok",
  failed: "danger", error: "danger", stale: "warn", rejected: "neutral", unsupported: "neutral",
};

export function categoryLabel(c: string | null | undefined) {
  return c ? humanize(c) : "Unclassified";
}

/** Humanize key-shaped tokens inside a "a · b · c" value ("seat_addon · $205.33 · paid" → "Seat addon · $205.33 · Paid"). */
export function humanizeInline(value: string): string {
  return value.split(" · ").map((t) => (/^[a-z]+(_[a-z]+)*$/.test(t) ? humanize(t) : t)).join(" · ");
}
