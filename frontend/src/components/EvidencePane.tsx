import type { RequestDetail } from "../api";
import { PanelHeading, Tag, timeAgo } from "./ui";

export function EvidencePane({ detail: d, onCite }: { detail: RequestDetail | null; onCite: (id: string) => void }) {
  if (!d) return <aside className="hidden border-l border-zinc-200 bg-zinc-50 xl:block" />;
  const c = d.proposal?.version.content;
  const history = [
    ...(d.proposal?.versions ?? []).map((v) => ({ at: v.created_at, text: `Version ${v.version} by ${v.author}${v.edit_note ? ` (${v.edit_note})` : ""}`, tone: "zinc" as const })),
    ...d.approvals.map((a) => ({ at: a.created_at, text: `${a.decision === "approved" ? "Approved" : "Rejected"} by ${a.actor}${a.status === "invalidated" ? `, invalidated: ${a.invalidated_reason}` : ""}${a.reason ? `: ${a.reason}` : ""}`, tone: a.status === "invalidated" ? ("amber" as const) : ("teal" as const) })),
    ...d.executions.map((e) => ({ at: e.created_at, text: `Execution ${e.status} via ${e.adapter} adapter after ${e.attempts} attempt(s), key ${e.idempotency_key}${e.last_error ? `: ${e.last_error}` : ""}`, tone: e.status === "failed" ? ("red" as const) : ("zinc" as const) })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <aside className="min-h-0 space-y-6 overflow-y-auto border-l border-zinc-200 bg-zinc-50 px-4 py-5" data-testid="evidence-pane">
      <section>
        <PanelHeading aside={<span className="text-xs text-zinc-400">from tools, not the model</span>}>Account facts</PanelHeading>
        {c ? (
          <dl className="space-y-2 text-sm">
            {c.account_facts.map((f) => (
              <div key={f.label}>
                <dt className="text-xs text-zinc-500">{f.label}</dt>
                <dd className="text-zinc-900">{f.value}</dd>
              </div>
            ))}
          </dl>
        ) : <p className="text-sm text-zinc-500">Facts appear after the workflow looks up the authorized customer.</p>}
      </section>

      <section>
        <PanelHeading>Sources</PanelHeading>
        {c && c.citations.length > 0 ? (
          <ol className="space-y-2">
            {c.citations.map((ct, i) => (
              <li key={ct.chunk_id}>
                <button onClick={() => onCite(ct.chunk_id)} className="w-full rounded-md bg-white p-2.5 text-left ring-1 ring-inset ring-zinc-200 hover:ring-teal-600" data-testid="citation">
                  <span className="text-xs font-medium text-teal-800">[{i + 1}] {ct.doc_title} v{ct.version}</span>
                  <span className="block text-sm font-medium text-zinc-900">{ct.section}</span>
                  <span className="mt-0.5 block text-xs text-zinc-600">{ct.claim}</span>
                </button>
              </li>
            ))}
          </ol>
        ) : <p className="text-sm text-zinc-500">No citations yet.</p>}
      </section>

      <section>
        <PanelHeading>Tickets</PanelHeading>
        {d.tickets.length ? d.tickets.map((t) => (
          <div key={t.id} className="mb-2 rounded-md bg-white p-2.5 text-sm ring-1 ring-inset ring-zinc-200" data-testid="ticket">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-zinc-900">{t.number}</span>
              <span className="flex gap-1">{t.sandbox && <Tag>Demo sandbox</Tag>}<Tag tone="teal">{t.status.replace("_", " ")}</Tag></span>
            </div>
            <p className="mt-1 text-zinc-800">{t.subject}</p>
            <p className="text-xs text-zinc-500">{t.group}, {t.priority} priority, {t.adapter} adapter</p>
          </div>
        )) : <p className="text-sm text-zinc-500">No ticket has been created or changed for this request.</p>}
      </section>

      <section>
        <PanelHeading>Action history</PanelHeading>
        {history.length ? (
          <ul className="space-y-1.5 text-sm" data-testid="history">
            {history.map((h, i) => (
              <li key={i} className={h.tone === "red" ? "text-red-800" : h.tone === "amber" ? "text-amber-800" : "text-zinc-700"}>
                {h.text} <span className="text-xs text-zinc-400">{timeAgo(h.at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-zinc-500">No review actions yet.</p>}
      </section>
    </aside>
  );
}
