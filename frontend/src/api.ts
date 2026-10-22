// Typed API client. Cookies carry the session; the custom header is the CSRF guard.

export type TicketAction = {
  type: "none" | "create_ticket" | "add_note";
  subject?: string | null;
  body?: string | null;
  priority?: "low" | "normal" | "high" | "urgent" | null;
  group?: string | null;
  status?: "open" | "pending_customer" | "solved" | null;
  ticket_id?: string | null;
};

export type Citation = {
  chunk_id: string; document_id: string; document_version_id: string; version: number;
  doc_slug: string; doc_title: string; section: string; claim: string; excerpt: string;
};

export type ProposalContent = {
  summary: string; category: string; priority: string; justification: string;
  next_action: "resolve" | "clarify" | "escalate";
  account_facts: { label: string; value: string; source: string }[];
  draft_reply: string; citations: Citation[]; ticket_action: TicketAction;
  missing_info: string[]; escalation_reason: string | null;
  rule_hits: { key: string; name: string; effect: string }[];
  risk_flags: string[]; provider_label: string; simulated: boolean;
};

export type Customer = { id: string; company_name: string; account_ref: string; is_synthetic: boolean };

export type RequestSummary = {
  id: string; subject: string; from_name: string; from_email: string; state: string;
  state_reason: string | null; category: string | null; priority: string | null; resolution: string | null;
  scenario_key: string | null; is_template: boolean; source_request_id: string | null;
  received_at: string; updated_at: string; customer: Customer | null;
};

export type Ticket = {
  id: string; number: string; subject: string; body: string; category: string; priority: string;
  status: string; group: string; source: string; adapter: string; sandbox: boolean;
  notes: { body: string; at: string }[]; created_at: string; request_id: string | null;
};

export type TimelineEvent = {
  id: number; event: string; actor: string; tool_name: string | null;
  summary: Record<string, unknown>; duration_ms: number | null; error: string | null; created_at: string;
};

export type ProposalUsage = {
  provider?: "simulated" | "live"; label?: string; model?: string | null; latency_ms?: number;
  input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number;
  api_calls?: number; tool_steps?: number; retries?: number;
};

export type AiRun = {
  id: string; provider: "simulated" | "live"; model: string | null; status: string; latency_ms: number | null;
  input_tokens: number; output_tokens: number; tool_steps: number; api_calls: number; error: string | null; created_at: string;
};

export type RequestDetail = RequestSummary & {
  body: string;
  ai_runs: AiRun[];
  proposal: null | {
    id: string; provider: string; status: string; current_version: number; usage: ProposalUsage;
    version: { id: string; version: number; content: ProposalContent; action_hash: string; author: string;
               edit_note: string | null; created_at: string };
    versions: { id: string; version: number; author: string; edit_note: string | null; created_at: string }[];
  };
  approvals: { id: string; decision: string; actor: string; status: string; reason: string | null;
               invalidated_reason: string | null; version_id: string; created_at: string }[];
  executions: { id: string; status: string; attempts: number; last_error: string | null; adapter: string;
                action_type: string; idempotency_key: string; ticket_id: string | null; created_at: string }[];
  tickets: Ticket[];
  timeline: TimelineEvent[];
  allowed_actions: { run: boolean; edit: boolean; approve: boolean; reject: boolean; retry: boolean };
};

export type Scenario = { key: string; label: string; description: string };
export type Meta = {
  mode: "demo" | "live"; effective_mode: "demo" | "live"; provider_label: string; live_model: string | null;
  live_configured: boolean; live_for_visitors: boolean;
  reviewer: { email: string; name: string } | null;
  workspaces: { slug: string; name: string; profile: Record<string, unknown>; demo_scenarios: Scenario[]; ticket_groups: string[] }[];
};

export type Passage = {
  chunk_id: string; doc_slug: string; doc_title: string; version: number; version_status: string;
  section: string; text: string; active: boolean; document_content: string;
};

type UsageTotals = { runs: number; errors: number; input_tokens: number; output_tokens: number; total_tokens: number };
export type AiStatus = {
  mode: "demo" | "live"; provider_label: string; model: string; effort: string; refusal_fallback: boolean;
  key_configured: boolean; live_for_visitors: boolean;
  budget: { monthly_token_budget: number; tokens_used: number; tokens_remaining: number; monthly_usd_budget: number | null;
            cost_usd: number | null; pricing: null | { input_per_mtok_usd: number; output_per_mtok_usd: number; source: string };
            period_start: string };
  usage_this_month: { live: UsageTotals & { cost_usd: number | null }; simulated: UsageTotals };
  limits: Record<string, number>;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "X-ResolveOps": "1", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

const w = (ws: string) => `/api/w/${ws}`;

export const api = {
  meta: () => call<Meta>("GET", "/api/meta"),
  startDemo: () => call<{ demo_session: string }>("POST", "/api/demo/session"),
  resetDemo: () => call<{ deleted: Record<string, number> }>("POST", "/api/demo/reset"),
  login: (email: string, password: string) => call<{ email: string }>("POST", "/api/auth/login", { email, password }),
  logout: () => call("POST", "/api/auth/logout"),
  requests: (ws: string, q: { state?: string; category?: string }) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return call<{ requests: RequestSummary[] }>("GET", `${w(ws)}/requests?${p}`);
  },
  request: (ws: string, id: string) => call<RequestDetail>("GET", `${w(ws)}/requests/${id}`),
  runScenario: (ws: string, key: string) => call<RequestDetail>("POST", `${w(ws)}/scenarios/${key}/run`),
  run: (ws: string, id: string) => call<RequestDetail>("POST", `${w(ws)}/requests/${id}/run`),
  edit: (ws: string, id: string, body: object) => call<RequestDetail>("PUT", `${w(ws)}/requests/${id}/proposal`, body),
  approve: (ws: string, id: string, versionId: string, hash: string) =>
    call<RequestDetail>("POST", `${w(ws)}/requests/${id}/approve`, { proposal_version_id: versionId, action_hash: hash }),
  reject: (ws: string, id: string, versionId: string, reason: string) =>
    call<RequestDetail>("POST", `${w(ws)}/requests/${id}/reject`, { proposal_version_id: versionId, reason }),
  retry: (ws: string, id: string) => call<RequestDetail>("POST", `${w(ws)}/requests/${id}/retry`),
  passage: (ws: string, chunkId: string) => call<Passage>("GET", `${w(ws)}/chunks/${chunkId}`),
  customers: (ws: string) =>
    call<{ customers: (Customer & { contact_name: string; plan: string })[] }>("GET", `${w(ws)}/customers`),
  customerSession: (ws: string, customerId: string) =>
    call<{ customer: Customer }>("POST", `${w(ws)}/customer-session`, { customer_id: customerId }),
  submit: (ws: string, subject: string, body: string) =>
    call<RequestDetail>("POST", `${w(ws)}/requests`, { subject, body }),
  aiStatus: (ws: string) => call<AiStatus>("GET", `${w(ws)}/ai/status`),
  tickets: (ws: string) => call<{ tickets: Ticket[] }>("GET", `${w(ws)}/tickets`),
};
