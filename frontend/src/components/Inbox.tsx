import type { KeyboardEvent } from "react";
import { ChevronRight, Inbox as InboxIcon, SearchX } from "lucide-react";
import type { RequestSummary } from "../api";
import { categoryLabel, humanize, requestStatus } from "../labels";
import { HelpTip, StatusLabel, timeAgo } from "./ui";

export { categoryLabel };
export type Filters = { state: string; category: string };

const STATES = ["", "awaiting_review", "stale", "completed", "failed", "rejected", "unsupported", "error"];
const CATEGORIES = ["", "access", "billing", "product_issue"];
const STATE_OPTION: Record<string, string> = {
  awaiting_review: "Awaiting review", stale: "Stale evidence", completed: "Completed", failed: "Execution failed",
  rejected: "Rejected", unsupported: "Not supported", error: "Processing error",
};

/** Arrow keys move between rows; Home/End jump to the ends. */
function onListKey(e: KeyboardEvent<HTMLElement>) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const rows = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("[data-row]")].filter((r) => r.offsetParent !== null);
  const i = rows.indexOf(document.activeElement as HTMLButtonElement);
  const next = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : e.key === "ArrowDown" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i - 1);
  if (rows[next]) { e.preventDefault(); rows[next].focus(); }
}

function Row({ r, selected, onSelect }: { r: RequestSummary; selected: boolean; onSelect: () => void }) {
  const customer = r.customer?.company_name ?? r.from_name;
  const status = requestStatus(r);
  const urgent = r.priority === "high" || r.priority === "urgent";
  return (
    <li>
      <button data-row onClick={onSelect} aria-current={selected || undefined} data-testid="inbox-row"
        className={`group relative block w-full rounded-md px-3 py-2.5 text-left transition-colors duration-150 ${selected
          ? "bg-accent-soft ring-1 ring-inset ring-accent-line"
          : "hover:bg-surface"}`}>
        <span className="flex items-baseline gap-2">
          <span className={`min-w-0 flex-1 truncate text-ui font-semibold ${selected ? "text-fg" : "text-fg"}`} title={r.subject}>{r.subject}</span>
          <span className="shrink-0 text-2xs tabular-nums text-fg-subtle">{timeAgo(r.received_at)}</span>
        </span>
        <span className="mt-0.5 block truncate text-xs text-fg-muted" title={`${customer} · ${r.from_name}`}>
          {customer}<span className="text-fg-subtle"> · {r.from_name}</span>
        </span>
        {r.preview && <span className="mt-1 line-clamp-2 text-xs leading-snug text-fg-subtle [overflow-wrap:anywhere]" data-testid="inbox-preview">{r.preview}</span>}
        <span className="mt-1.5 flex min-w-0 items-center gap-2">
          <StatusLabel status={status} className="shrink-0" />
          {status.key === "needs_info" && status.detail && <span className="min-w-0 truncate text-2xs text-fg-subtle">{status.detail}</span>}
          {r.category && <span className="min-w-0 truncate text-2xs text-fg-subtle">{categoryLabel(r.category)}</span>}
          {urgent && <span className="ml-auto shrink-0 text-2xs font-semibold text-danger">{humanize(r.priority)}</span>}
        </span>
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
  scopeHelp: string;
  loading: boolean;
  query: string;
}) {
  const { requests, selectedId, onSelect, filters, setFilters, scopeLabel, scopeHelp, loading, query } = props;
  const q = query.trim().toLowerCase();
  const matches = (r: RequestSummary) => !q || [r.subject, r.from_name, r.from_email, r.customer?.company_name ?? "", r.preview ?? ""].some((s) => s.toLowerCase().includes(q));
  const visible = requests.filter(matches);
  const mine = visible.filter((r) => !r.is_template);
  const templates = visible.filter((r) => r.is_template);
  const filtered = !!(filters.state || filters.category || q);
  const select = "h-7 min-w-0 flex-1 rounded-md border-0 bg-surface pl-2 pr-7 text-xs text-fg ring-1 ring-inset ring-line-strong hover:ring-fg-subtle/60";

  return (
    <aside className="flex h-full min-h-0 flex-col bg-canvas" aria-label="Inbox">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <label className="sr-only" htmlFor="filter-state">Filter by state</label>
        <select id="filter-state" className={select} value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
          {STATES.map((s) => <option key={s} value={s}>{s ? STATE_OPTION[s] : "All states"}</option>)}
        </select>
        <label className="sr-only" htmlFor="filter-category">Filter by category</label>
        <select id="filter-category" className={select} value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c ? categoryLabel(c) : "All categories"}</option>)}
        </select>
      </div>
      <div className="pane-scroll min-h-0 flex-1 overflow-y-auto px-2 pb-4" data-testid="inbox" onKeyDown={onListKey}>
        <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-3">
          <h2 className="text-xs font-semibold text-fg-muted">{scopeLabel}</h2>
          <span className="text-xs tabular-nums text-fg-subtle">{mine.length}</span>
          <HelpTip label={`About ${scopeLabel.toLowerCase()}`}>{scopeHelp}</HelpTip>
        </div>
        {loading && requests.length === 0 && (
          <div className="space-y-1 px-1" aria-label="Loading requests">
            {[0, 1, 2].map((i) => <div key={i} className="anim-skeleton h-[72px] rounded-md bg-sunken" />)}
          </div>
        )}
        {!loading && mine.length === 0 && (
          <div className="mx-1 flex items-start gap-2.5 rounded-md border border-dashed border-line-strong px-3 py-3 text-xs text-fg-muted">
            {filtered ? <SearchX aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} /> : <InboxIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} />}
            <p>{filtered ? "No requests match these filters." : <>Nothing here yet. Use <span className="font-medium text-fg">Try a scenario</span> above, or open an example request below.</>}</p>
          </div>
        )}
        <ul className="space-y-0.5">{mine.map((r) => <Row key={r.id} r={r} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />)}</ul>

        {!(loading && requests.length === 0) && <details open className="group/s mt-3" data-testid="seeded-section">
          <summary className="flex cursor-pointer select-none items-center gap-1.5 rounded-md px-2 py-1.5 hover:bg-sunken">
            <ChevronRight aria-hidden className="size-3.5 text-fg-subtle transition-transform duration-150 group-open/s:rotate-90" strokeWidth={2} />
            <h2 className="text-xs font-semibold text-fg-muted">Example requests</h2>
            <span className="text-xs tabular-nums text-fg-subtle">{templates.length}</span>
            <span className="ml-auto text-2xs text-fg-subtle">Shared, read-only</span>
          </summary>
          {templates.length === 0
            ? <p className="px-3 py-2 text-xs text-fg-subtle">{filtered ? "No example requests match." : "No example requests in this workspace."}</p>
            : <ul className="mt-0.5 space-y-0.5">{templates.map((r) => <Row key={r.id} r={r} selected={r.id === selectedId} onSelect={() => onSelect(r.id)} />)}</ul>}
        </details>}
      </div>
    </aside>
  );
}
