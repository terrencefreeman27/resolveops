import type { RequestSummary } from "../api";
import { StateBadge, Tag, timeAgo } from "./ui";

export type Filters = { state: string; category: string };

const STATES = ["", "awaiting_review", "stale", "completed", "failed", "rejected", "unsupported", "error"];
const CATEGORIES = ["", "access", "billing", "product_issue"];
const CATEGORY_LABEL: Record<string, string> = { access: "Access", billing: "Billing", product_issue: "Product issue" };

export function categoryLabel(c: string | null) {
  return c ? CATEGORY_LABEL[c] ?? c : "Unclassified";
}

function Row({ r, selected, onSelect }: { r: RequestSummary; selected: boolean; onSelect: () => void }) {
  return (
    <li>
      <button
        onClick={onSelect}
        aria-current={selected}
        className={`w-full rounded-md px-3 py-2.5 text-left transition-colors ${selected ? "bg-white ring-1 ring-teal-600 shadow-sm" : "hover:bg-white"}`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-medium text-zinc-900">{r.customer?.company_name ?? r.from_name}</span>
          <span className="shrink-0 text-xs text-zinc-500">{timeAgo(r.received_at)}</span>
        </div>
        <p className="mt-0.5 truncate text-sm text-zinc-600">{r.subject}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <StateBadge state={r.state} template={r.is_template} />
          {r.category && <Tag>{categoryLabel(r.category)}</Tag>}
          {r.priority === "high" || r.priority === "urgent" ? <Tag tone="red">{r.priority}</Tag> : null}
        </div>
      </button>
    </li>
  );
}

export function Inbox(props: {
  requests: RequestSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  filters: Filters;
  setFilters: (f: Filters) => void;
  scopeLabel: string;
  loading: boolean;
}) {
  const { requests, selectedId, onSelect, filters, setFilters, scopeLabel, loading } = props;
  const mine = requests.filter((r) => !r.is_template);
  const templates = requests.filter((r) => r.is_template);
  const select = "w-full rounded-md border-0 bg-white py-1.5 pl-2 pr-7 text-sm ring-1 ring-inset ring-zinc-300";
  return (
    <aside className="flex min-h-0 flex-col border-r border-zinc-200 bg-zinc-100/60">
      <div className="grid grid-cols-2 gap-2 border-b border-zinc-200 p-3">
        <label className="grid gap-1 text-xs font-medium text-zinc-600">
          State
          <select className={select} value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
            {STATES.map((s) => <option key={s} value={s}>{s ? s.replace("_", " ") : "All"}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-zinc-600">
          Category
          <select className={select} value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c ? categoryLabel(c) : "All"}</option>)}
          </select>
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2" data-testid="inbox">
        {loading && requests.length === 0 && (
          <div className="space-y-2 p-1">{[0, 1, 2, 3].map((i) => <div key={i} className="h-16 animate-pulse rounded-md bg-zinc-200/70" />)}</div>
        )}
        <h2 className="px-2 pb-1 pt-2 text-xs font-semibold text-zinc-500">{scopeLabel} ({mine.length})</h2>
        {mine.length === 0 && !loading && (
          <p className="px-2 pb-2 text-sm text-zinc-500">Nothing here yet. Run a demo scenario or open a seeded request below.</p>
        )}
        <ul className="space-y-1">{mine.map((r) => <Row key={r.id} r={r} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />)}</ul>
        <h2 className="px-2 pb-1 pt-4 text-xs font-semibold text-zinc-500">Seeded inbox, shared and read-only ({templates.length})</h2>
        <ul className="space-y-1">{templates.map((r) => <Row key={r.id} r={r} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />)}</ul>
      </div>
    </aside>
  );
}
