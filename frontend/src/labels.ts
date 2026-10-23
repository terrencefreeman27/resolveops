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
  failed: "Execution failed", error: "Processing error", stale: "Stale evidence", rejected: "Rejected", unsupported: "Not supported",
};
export const stateLabel = (s: string) => STATE_LABEL[s] ?? humanize(s);

export type Tone = "neutral" | "accent" | "warn" | "danger" | "ok";

export function categoryLabel(c: string | null | undefined) {
  return c ? humanize(c) : "Unclassified";
}

/** Humanize key-shaped tokens inside a "a · b · c" value ("seat_addon · $205.33 · paid" → "Seat addon · $205.33 · Paid"). */
export function humanizeInline(value: string): string {
  return value.split(" · ").map((t) => (/^[a-z]+(_[a-z]+)*$/.test(t) ? humanize(t) : t)).join(" · ");
}

// ---------------------------------------------------------------------------------------------
// Workflow status: one mapping from the request's actual state (+ the current proposal's next
// action) to what the UI shows. No invented intermediate states: every status below corresponds to
// a stored request state; "Needs information" is an awaiting/approved proposal whose next action is clarify.

export type StatusKey =
  | "ready" | "processing" | "needs_info" | "awaiting_review" | "completed" | "rejected"
  | "failed" | "error" | "stale" | "unsupported";

export type RequestStatus = {
  key: StatusKey;
  /** Short label for rows and chips. */
  label: string;
  /** Secondary detail, e.g. "Awaiting review" under "Needs information". */
  detail: string | null;
  tone: Tone;
};

type StatusInput = { state: string; is_template: boolean; next_action?: string | null; resolution?: string | null };

const IN_FLIGHT = new Set(["classified", "context_resolved", "retrieved", "approved", "executing"]);

export function requestStatus(r: StatusInput): RequestStatus {
  const s = (key: StatusKey, label: string, tone: Tone, detail: string | null = null): RequestStatus => ({ key, label, detail, tone });
  if (r.is_template) return s("ready", "Not processed", "neutral", "Example request");
  const clarify = r.next_action === "clarify" || r.resolution === "clarification_requested";
  switch (r.state) {
    case "received": return s("ready", "Ready to process", "neutral");
    case "awaiting_review": return clarify ? s("needs_info", "Needs information", "warn", "Awaiting review") : s("awaiting_review", "Awaiting review", "accent");
    case "completed": return clarify ? s("needs_info", "Needs information", "warn", "Clarification approved") : s("completed", "Completed", "ok");
    case "rejected": return s("rejected", "Rejected", "neutral");
    case "failed": return s("failed", "Execution failed", "danger", "Retry available");
    case "error": return s("error", "Processing error", "danger");
    case "stale": return s("stale", "Stale evidence", "warn", "Needs reprocessing");
    case "unsupported": return s("unsupported", "Not supported", "neutral");
    default: return IN_FLIGHT.has(r.state) ? s("processing", "Processing", "accent", STATE_LABEL[r.state] ?? null) : s("processing", humanize(r.state), "neutral");
  }
}

// ---------------------------------------------------------------------------------------------
// Approval copy, derived from the proposed ticket action type and the adapter the server reports it
// would execute through (proposal.planned_adapter). Keep this the only place that words approval.

export type ActionInput = {
  type: "none" | "create_ticket" | "add_note";
  group?: string | null; priority?: string | null; status?: string | null; ticket_id?: string | null;
};
export type ApprovalCopy = {
  /** Heading for the review section. */
  reviewTitle: string;
  /** Approve button text. */
  approveLabel: string;
  /** What approving does, in one or two sentences. */
  consequence: string;
  /** Does approval change a ticket (true) or only record the reviewed draft (false)? */
  changesTicket: boolean;
};

export function approvalCopy(ta: ActionInput, adapter: string | null | undefined): ApprovalCopy {
  const github = adapter === "github";
  if (ta.type === "create_ticket") {
    const where = github ? "an issue in the configured GitHub repository" : "an internal ticket";
    const pr = ta.priority ? `${humanize(ta.priority).toLowerCase()} priority` : null;
    const st = ta.status ? `status ${humanize(ta.status).toLowerCase()}` : null;
    const attrs = [pr, st].filter(Boolean).join(", ");
    return {
      reviewTitle: github ? "Review GitHub issue and reply draft" : "Review new ticket and reply draft",
      approveLabel: github ? "Approve and open GitHub issue" : "Approve and create ticket",
      consequence: `Approving creates ${where}${ta.group ? ` for ${ta.group}` : ""}${attrs ? ` (${attrs})` : ""} and records the reply draft. Nothing is sent to the customer.`,
      changesTicket: true,
    };
  }
  if (ta.type === "add_note") {
    const t = "the customer's existing ticket"; // ticket_id is an internal id; the number is shown after execution
    return {
      reviewTitle: "Review ticket note and reply draft",
      approveLabel: "Approve and add note",
      consequence: `Approving adds an internal note to ${t} and records the reply draft. Nothing is sent to the customer.`,
      changesTicket: true,
    };
  }
  return {
    reviewTitle: "Review reply draft",
    approveLabel: "Approve draft",
    consequence: "Approving only records this reviewed draft for your team to send. No ticket is created or changed, and nothing is sent to the customer.",
    changesTicket: false,
  };
}

/** Headline for a completed request, from what the execution actually did. */
export function completedTitle(actionType: string | null | undefined, tickets: { number: string; external_number?: number | null }[],
  resultNote?: string | null): string {
  const t = tickets[0];
  if (actionType === "create_ticket" && t) return t.external_number ? `GitHub issue #${t.external_number} opened` : `Ticket ${t.number} created`;
  if (actionType === "add_note" && t) return `Note added to ticket ${t.number}`;
  // The executor's own result line ("Ticket NS-903 updated") when the ticket isn't linked to this request.
  if ((actionType === "add_note" || actionType === "create_ticket") && resultNote) return resultNote;
  if (actionType === "add_note" || actionType === "create_ticket") return "Ticket action completed";
  return "Reply draft approved";
}
