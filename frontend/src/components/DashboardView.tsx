import { useEffect, useState } from "react";
import { api, type Dashboard, type EvalSuite, type RateStat, type RunBlock } from "../api";
import { Button, STATE_LABEL, Tag } from "./ui";

const CATEGORY_LABEL: Record<string, string> = {
  access: "Access", billing: "Billing", product_issue: "Product issue", unsupported: "Unsupported", unclassified: "Not classified",
};

function Section({ title, note, children, testid }: { title: string; note?: string; children: React.ReactNode; testid?: string }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4" data-testid={testid}>
      <h2 className="text-sm font-semibold text-zinc-900">{title}</h2>
      {note && <p className="mt-0.5 text-xs text-zinc-500">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tabular-nums text-zinc-900">{value}</p>
      {hint && <p className="text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

/** Counts as a table with one single-hue bar per row; the number is always printed, so the bar is never the only encoding. */
function CountTable({ rows, label, caption }: { rows: [string, number][]; label: (k: string) => string; caption: string }) {
  const max = Math.max(1, ...rows.map(([, n]) => n));
  if (!rows.length) return <p className="text-sm text-zinc-500">No requests yet.</p>;
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <tbody>
        {rows.map(([k, n]) => (
          <tr key={k} title={`${label(k)}: ${n}`}>
            <th scope="row" className="w-40 py-1 pr-3 text-left font-normal text-zinc-700">{label(k)}</th>
            <td className="py-1"><div className="h-2 rounded-r bg-teal-600" style={{ width: `${(n / max) * 100}%`, minWidth: 4 }} /></td>
            <td className="w-10 py-1 pl-3 text-right tabular-nums text-zinc-900">{n}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const pct = (r?: RateStat | null) => (r && r.total ? `${r.correct}/${r.total} (${Math.round((r.rate ?? 0) * 100)}%)` : "n/a");
const ms = (v: number | null) => (v === null ? "—" : `${v} ms`);

function Runs({ kind, b }: { kind: "simulated" | "live"; b: RunBlock }) {
  return (
    <div data-testid={`runs-${kind}`} className="rounded-md bg-zinc-50 p-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium text-zinc-900">{kind === "simulated" ? "Simulated AI" : "Live model"}</h3>
        <Tag tone={kind === "live" ? "teal" : "zinc"}>{kind === "live" ? "live" : "simulated"}</Tag>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-zinc-500">Runs</dt><dd className="tabular-nums">{b.runs}</dd></div>
        <div><dt className="text-xs text-zinc-500">Errors</dt><dd className="tabular-nums">{b.errors}</dd></div>
        <div><dt className="text-xs text-zinc-500">Median</dt><dd className="tabular-nums">{ms(b.latency_ms_median)}</dd></div>
        <div><dt className="text-xs text-zinc-500">p95</dt><dd className="tabular-nums">{ms(b.latency_ms_p95)}</dd></div>
        {kind === "live" && <>
          <div><dt className="text-xs text-zinc-500">Input tokens</dt><dd className="tabular-nums">{b.input_tokens ?? 0}</dd></div>
          <div><dt className="text-xs text-zinc-500">Output tokens</dt><dd className="tabular-nums">{b.output_tokens ?? 0}</dd></div>
          <div className="col-span-2"><dt className="text-xs text-zinc-500">Estimated cost</dt>
            <dd data-testid="cost">{b.cost?.usd != null ? `$${b.cost.usd}` : (b.cost?.note ?? "pricing not configured")}</dd></div>
        </>}
      </dl>
      {b.note && <p className="mt-2 text-xs text-zinc-500">{b.note}</p>}
      {kind === "live" && b.cost?.assumptions && (
        <p className="mt-2 text-xs text-zinc-500">Pricing assumptions: input ${String(b.cost.assumptions.input_per_mtok_usd)}/MTok,
          output ${String(b.cost.assumptions.output_per_mtok_usd)}/MTok ({String(b.cost.assumptions.source)}); excludes {String(b.cost.assumptions.excludes)}.</p>
      )}
    </div>
  );
}

function EvalCard({ s }: { s: EvalSuite }) {
  const h = s.headline;
  const notRun = s.status !== "run";
  const tone = notRun ? "zinc" : s.mode === "demo" ? "amber" : "teal";
  return (
    <div className="rounded-md border border-zinc-200 p-3" data-testid={`eval-${s.suite}-${s.mode.split(" ")[0]}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium text-zinc-900">{s.suite === "ai" ? "AI task eval" : "Backend checks"}</h3>
        <Tag tone={tone}>{notRun ? "Not run" : s.mode}</Tag>
        {s.label && <span className="text-xs font-medium text-zinc-700">{s.label}</span>}
      </div>
      <p className="mt-1 text-xs text-zinc-500">{s.file} · commit {s.git_commit}{s.dataset_version ? ` · dataset ${s.dataset_version}` : ""}</p>
      {notRun && s.command && <p className="mt-2 text-xs text-zinc-600">Command: <code className="break-all rounded bg-zinc-100 px-1">{s.command}</code></p>}
      {s.suite === "ai" && h && (
        <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-zinc-500">Coverage</dt><dd>{Object.entries(h.coverage ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</dd></div>
          <div><dt className="text-xs text-zinc-500">Correct next action (scored cases)</dt><dd className="tabular-nums">{pct(h.next_action)}</dd></div>
          <div><dt className="text-xs text-zinc-500">Classification</dt><dd className="tabular-nums">{pct(h.classification)}</dd></div>
          <div><dt className="text-xs text-zinc-500">Section recall (mean)</dt><dd className="tabular-nums">{h.recall_section_mean ?? "n/a"}</dd></div>
          <div><dt className="text-xs text-zinc-500">Citations valid (exist, retrieved, current)</dt><dd className="tabular-nums">{h.citations_valid}</dd></div>
          <div><dt className="text-xs text-zinc-500">Citation support (agent-labelled, unreviewed)</dt><dd>{Object.entries(h.citation_support_labels ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ")}</dd></div>
          <div><dt className="text-xs text-zinc-500">Clarify when expected</dt><dd className="tabular-nums">{pct(h.clarify_when_expected)}</dd></div>
          <div><dt className="text-xs text-zinc-500">Escalate when expected</dt><dd className="tabular-nums">{pct(h.escalate_when_expected)}</dd></div>
          <div><dt className="text-xs text-zinc-500">Must-not violations</dt><dd className="tabular-nums">{h.must_not_failures}</dd></div>
          <div><dt className="text-xs text-zinc-500">Prompt-only baseline</dt><dd>{s.baseline ?? "not run"}</dd></div>
        </dl>
      )}
      {s.suite === "backend" && h?.categories && (
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Backend checks by category</caption>
          <tbody>
            {Object.entries(h.categories).map(([k, v]) => (
              <tr key={k}><th scope="row" className="py-0.5 pr-3 text-left font-normal text-zinc-700">{k.replace(/_/g, " ")}</th><td className="text-right tabular-nums">{v}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function DashboardView({ ws, onOpenInbox }: { ws: string; onOpenInbox: () => void }) {
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.dashboard(ws).then((x) => { setD(x); setErr(null); }).catch((e: Error) => setErr(e.message));
  useEffect(() => { if (ws) load(); }, [ws]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <main className="p-6 text-sm text-red-800" role="alert">{err}</main>;
  if (!d) return <main className="p-6 text-sm text-zinc-500">Loading dashboard…</main>;
  const o = d.approval_outcomes;
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 space-y-4 p-4 xl:overflow-y-auto" data-testid="dashboard">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900">Dashboard</h1>
          <p className="text-sm text-zinc-600" data-testid="dashboard-scope">Scope: {d.scope}. No savings or business impact is estimated.</p>
        </div>
        <div className="flex gap-2"><Button variant="ghost" onClick={load}>Refresh</Button><Button onClick={onOpenInbox}>Back to inbox</Button></div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Requests by category" note={`${d.requests.total} processed request(s); seeded templates excluded.`} testid="dash-category">
          <CountTable caption="Requests by category" rows={Object.entries(d.requests.by_category).sort((a, b) => b[1] - a[1])} label={(k) => CATEGORY_LABEL[k] ?? k} />
        </Section>
        <Section title="Requests by state" testid="dash-state">
          <CountTable caption="Requests by state" rows={Object.entries(d.requests.by_state).sort((a, b) => b[1] - a[1])} label={(k) => STATE_LABEL[k] ?? k} />
        </Section>
        <Section title="Approval outcomes" note="Edited-then-approved means a reviewer changed the draft and approved the new version." testid="dash-approvals">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Stat label="Approved as drafted" value={o.approved_as_drafted} />
            <Stat label="Edited, then approved" value={o.edited_then_approved} />
            <Stat label="Rejected" value={o.rejected} />
            <Stat label="Approvals invalidated" value={o.approvals_invalidated} hint="by a later edit" />
            <Stat label="Proposals made stale" value={o.proposals_made_stale} hint="evidence or rules changed" />
          </div>
        </Section>
        <Section title="Ticket executions" testid="dash-executions">
          <div className="grid grid-cols-3 gap-4">
            <Stat label="Executions" value={d.executions.total} />
            <Stat label="Succeeded" value={d.executions.succeeded} />
            <Stat label="Failed" value={d.executions.failed} hint={`${d.executions.attempts_total} attempt(s) total`} />
          </div>
          {d.executions.recent_failures.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-red-800">
              {d.executions.recent_failures.map((f, i) => <li key={i}><span className="font-medium">Failed</span> · {f.adapter} · {f.attempts} attempt(s): {f.error}</li>)}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Latency and token usage" note="Simulated and live runs are reported separately and never combined." testid="dash-usage">
        <div className="grid gap-3 lg:grid-cols-2">
          <Runs kind="simulated" b={d.ai_runs.simulated} />
          <Runs kind="live" b={d.ai_runs.live} />
        </div>
      </Section>

      <Section title="Evaluation results" testid="dash-eval"
        note="Latest result file per suite and mode, from eval/results. These describe the synthetic v1 dataset, not this workspace's traffic. Demo results are simulated and are not evidence of AI performance.">
        {d.evaluation.available && d.evaluation.suites?.length
          ? <div className="grid gap-3 lg:grid-cols-3">{d.evaluation.suites.map((s) => <EvalCard key={s.file} s={s} />)}</div>
          : <p className="text-sm text-zinc-500">{d.evaluation.note ?? "No evaluation results yet."}</p>}
      </Section>
    </main>
  );
}
