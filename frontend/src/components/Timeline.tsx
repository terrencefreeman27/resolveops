import type { TimelineEvent } from "../api";

const EVENT_LABEL: Record<string, string> = {
  "workflow.started": "Workflow started", "state.changed": "State changed", "ai.classify": "AI: classify",
  "ai.synthesize": "AI: draft proposal", "tool.call": "Tool", "tool.error": "Tool error", "tool.rejected": "Tool rejected",
  "proposal.created": "Proposal created", "proposal.edited": "Proposal edited", "citation.rejected": "Citation rejected",
  "approval.granted": "Approved", "approval.rejected": "Rejected", "execution.attempt": "Execution attempt",
  "execution.succeeded": "Execution succeeded", "execution.failed": "Execution failed", "execution.retry": "Retry requested", "execution.adapter_switched": "Switched to internal tickets",
  "workflow.error": "Workflow error",
};

type Passage = { chunk_id: string; doc: string; version: number; section: string; score: number };

function Summary({ e, onCite }: { e: TimelineEvent; onCite: (id: string) => void }) {
  const s = e.summary as Record<string, unknown>;
  if (e.event === "state.changed") return <span>{String(s.from)} to {String(s.to)}{s.reason ? `: ${String(s.reason)}` : ""}</span>;
  if (e.tool_name === "search_knowledge_base" && s.result) {
    const args = s.args as { query: string };
    const passages = (s.result as { passages: Passage[] }).passages;
    return (
      <div>
        <p>Query "{args.query}", {passages.length} passages</p>
        <ul className="mt-1 space-y-0.5">
          {passages.map((p) => (
            <li key={p.chunk_id}>
              <button className="text-left text-teal-800 hover:underline" onClick={() => onCite(p.chunk_id)}>
                {p.doc} v{p.version}, {p.section}
              </button>
              <span className="ml-1 text-zinc-500">score {p.score.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const body = s.result ?? s;
  const entries = Object.entries(body as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return null;
  return (
    <span className="break-words">
      {entries.map(([k, v], i) => (
        <span key={k}>{i > 0 && ", "}<span className="text-zinc-500">{k.replaceAll("_", " ")}:</span> {Array.isArray(v) ? v.join("; ") || "none" : typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
      ))}
    </span>
  );
}

export function Timeline({ events, onCite }: { events: TimelineEvent[]; onCite: (id: string) => void }) {
  const errors = events.filter((e) => e.error).length;
  return (
    <details className="group rounded-lg ring-1 ring-inset ring-zinc-200" data-testid="timeline">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium text-zinc-800">
        <span>Activity timeline ({events.length} events{errors ? `, ${errors} errors` : ""})</span>
        <span className="text-zinc-400 transition-transform group-open:rotate-90">&rsaquo;</span>
      </summary>
      <ol className="space-y-2 border-t border-zinc-200 px-4 py-3">
        {events.map((e) => (
          <li key={e.id} className="grid grid-cols-[8.5rem_minmax(0,1fr)_auto] gap-3 text-xs">
            <span className={`min-w-0 font-medium ${e.error ? "text-red-700" : "text-zinc-700"}`}>
              {EVENT_LABEL[e.event] ?? e.event}
              {e.tool_name && <span className="block font-mono font-normal text-zinc-500 [overflow-wrap:anywhere]">
                {e.tool_name.split("_").map((part, i) => <span key={i}>{i > 0 && <>_<wbr /></>}{part}</span>)}</span>}
            </span>
            <div className="min-w-0 text-zinc-700">
              <Summary e={e} onCite={onCite} />
              {e.error && <p className="mt-0.5 text-red-700">{e.error}</p>}
              <p className="text-zinc-500">{e.actor}</p>
            </div>
            <span className="font-mono text-zinc-500">{e.duration_ms !== null ? `${e.duration_ms} ms` : ""}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
