import { useState } from "react";
import { ArrowRight, BadgeCheck, ChevronRight, CircleAlert, CircleX, FilePen, Play, Search, Send, Sparkles, Wrench, type LucideIcon } from "lucide-react";
import type { TimelineEvent } from "../api";
import { humanize, stateLabel } from "../labels";

const EVENT_LABEL: Record<string, string> = {
  "workflow.started": "Workflow started", "state.changed": "State changed", "ai.classify": "Classify request",
  "ai.synthesize": "Draft proposal", "tool.call": "Tool", "tool.error": "Tool error", "tool.rejected": "Tool rejected",
  "proposal.created": "Proposal created", "proposal.edited": "Proposal edited", "citation.rejected": "Citation rejected",
  "approval.granted": "Approved", "approval.rejected": "Rejected", "execution.attempt": "Execution attempt",
  "execution.succeeded": "Execution succeeded", "execution.failed": "Execution failed", "execution.retry": "Retry requested", "execution.adapter_switched": "Switched to internal tickets",
  "workflow.error": "Workflow error",
};

function iconFor(e: TimelineEvent): LucideIcon {
  if (e.error || e.event.endsWith(".error") || e.event.endsWith(".failed")) return CircleAlert;
  if (e.tool_name === "search_knowledge_base") return Search;
  if (e.event.startsWith("tool.")) return Wrench;
  if (e.event.startsWith("ai.")) return Sparkles;
  if (e.event === "state.changed") return ArrowRight;
  if (e.event.startsWith("proposal.")) return FilePen;
  if (e.event === "approval.granted") return BadgeCheck;
  if (e.event === "approval.rejected") return CircleX;
  if (e.event.startsWith("execution.")) return Send;
  return Play;
}

export type Passage = { chunk_id: string; doc: string; version: number; section: string; score: number };

function title(e: TimelineEvent) {
  if (e.tool_name) return humanize(e.tool_name);
  return EVENT_LABEL[e.event] ?? humanize(e.event.replace(".", " "));
}

/** One-line summary shown on the collapsed row. */
export function brief(e: TimelineEvent): string {
  const s = e.summary as Record<string, unknown>;
  if (e.event === "state.changed") return `${stateLabel(String(s.from))} → ${stateLabel(String(s.to))}`;
  if (e.tool_name === "search_knowledge_base" && s.result) {
    const n = (s.result as { passages: Passage[] }).passages.length;
    return `“${(s.args as { query: string }).query}” · ${n} passage${n === 1 ? "" : "s"}`;
  }
  const body = (s.result ?? s) as Record<string, unknown>;
  return Object.entries(body).filter(([, v]) => v !== null && v !== undefined && v !== "" && typeof v !== "object")
    .slice(0, 3).map(([k, v]) => `${humanize(k)}: ${/^[a-z]+(_[a-z]+)+$/.test(String(v)) ? humanize(String(v)) : String(v)}`).join(" · ");
}

function Value({ v }: { v: unknown }) {
  if (Array.isArray(v)) return <>{v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join("; ") : "none"}</>;
  if (v && typeof v === "object") return <>{JSON.stringify(v)}</>;
  return <>{String(v)}</>;
}

function Payload({ label, data }: { label: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!entries.length) return null;
  return (
    <div>
      <p className="text-2xs font-semibold text-fg-subtle">{label}</p>
      <dl className="mt-1 grid grid-cols-[minmax(6rem,auto)_minmax(0,1fr)] gap-x-3 gap-y-0.5 rounded-md bg-canvas px-3 py-2 font-mono text-[11.5px] leading-relaxed">
        {entries.map(([k, v]) => (
          <div key={k} className="contents"><dt className="text-fg-subtle">{k}</dt><dd className="text-fg [overflow-wrap:anywhere]"><Value v={v} /></dd></div>
        ))}
      </dl>
    </div>
  );
}

function Details({ e, onCite }: { e: TimelineEvent; onCite: (id: string) => void }) {
  const s = e.summary as Record<string, unknown>;
  if (e.tool_name === "search_knowledge_base" && s.result) {
    const passages = (s.result as { passages: Passage[] }).passages;
    return (
      <ul className="space-y-0.5">
        {passages.map((p) => (
          <li key={p.chunk_id} className="flex items-baseline justify-between gap-3 text-xs">
            <button className="min-w-0 truncate text-left text-accent-strong hover:underline" onClick={() => onCite(p.chunk_id)}>{p.doc} v{p.version}, {p.section}</button>
            <span className="shrink-0 font-mono text-2xs text-fg-subtle">score {p.score.toFixed(2)}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (e.event === "state.changed") return s.reason ? <p className="text-xs text-fg-muted">{String(s.reason)}</p> : null;
  if (s.args || s.result) return <div className="space-y-2"><Payload label="Arguments" data={s.args as Record<string, unknown>} /><Payload label="Result" data={s.result as Record<string, unknown>} /></div>;
  return <Payload label="Details" data={s} />;
}

function Step({ e, onCite }: { e: TimelineEvent; onCite: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const Icon = iconFor(e);
  const err = !!e.error || e.event.endsWith(".error") || e.event.endsWith(".failed");
  const line = brief(e);
  const id = `step-${e.id}`;
  return (
    <li className="relative">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
        className="grid w-full grid-cols-[1rem_1.25rem_minmax(0,1fr)_auto] items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-canvas">
        <ChevronRight aria-hidden className={`mt-0.5 size-3.5 text-fg-subtle transition-transform duration-150 ${open ? "rotate-90" : ""}`} strokeWidth={2} />
        <span className={`mt-px grid size-5 place-items-center rounded ${err ? "bg-danger-soft text-danger" : "bg-sunken text-fg-muted"}`}>
          <Icon aria-hidden className="size-3" strokeWidth={2} />
        </span>
        <span className="min-w-0">
          <span className={`block text-xs font-medium ${err ? "text-danger" : "text-fg"}`}>{title(e)}</span>
          {line && <span className="block truncate text-xs text-fg-subtle">{line}</span>}
        </span>
        <span className="pt-px font-mono text-2xs tabular-nums text-fg-subtle">{e.duration_ms !== null ? `${e.duration_ms} ms` : ""}</span>
      </button>
      {open && (
        <div id={id} className="mb-2 ml-[2.75rem] mr-2 space-y-1.5">
          {e.error && <p className="text-xs text-danger">{e.error}</p>}
          <Details e={e} onCite={onCite} />
          <p className="text-2xs text-fg-subtle">Actor: {e.actor} · {e.event}{e.tool_name ? ` · ${e.tool_name}` : ""}</p>
        </div>
      )}
    </li>
  );
}

/** Every recorded audit event for the request, in order (the raw log behind Activity). */
export function EventLog({ events, onCite }: { events: TimelineEvent[]; onCite: (id: string) => void }) {
  return <ol className="py-1" data-testid="event-log">{events.map((e) => <Step key={e.id} e={e} onCite={onCite} />)}</ol>;
}
