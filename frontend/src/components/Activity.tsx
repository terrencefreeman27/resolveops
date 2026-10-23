import type { ReactNode } from "react";
import { ChevronRight, ExternalLink } from "lucide-react";
import type { RequestDetail, TimelineEvent } from "../api";
import { humanize } from "../labels";
import { EventLog, brief, type Passage } from "./Timeline";
import { Disclosure } from "./ui";

// Activity: the execution evidence the backend records for a request (audit log, AI runs, proposal
// usage, approvals, executions), arranged for inspection. Nothing here is inferred or reconstructed;
// where the backend doesn't record something, the section says "Not recorded".

const ms = (v: number | null | undefined) => v == null ? "Not recorded" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
const num = (v: number | null | undefined) => (v ?? 0).toLocaleString("en-US");
const between = (a: string | null | undefined, b: string | null | undefined) =>
  a && b ? Math.max(0, new Date(b).getTime() - new Date(a).getTime()) : null;
const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });

/** The executor's own result line for the last successful execution ("Ticket NS-1001 created"). */
export function executionResult(d: RequestDetail): string | null {
  const e = [...d.timeline].reverse().find((x) => x.event === "execution.succeeded");
  const r = (e?.summary as { result?: unknown } | undefined)?.result;
  return typeof r === "string" ? r : null;
}

const isError = (e: TimelineEvent) => !!e.error || e.event.endsWith(".error") || e.event.endsWith(".failed") || e.event === "tool.rejected";

function Block({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  return (
    <section className="space-y-1.5 border-t border-line px-4 py-3" data-testid={testId}>
      <h3 className="text-xs font-semibold text-fg-muted">{title}</h3>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,30%)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-subtle">{k}</dt>
          <dd className={`[overflow-wrap:anywhere] ${v === "Not recorded" ? "italic text-fg-subtle" : "text-fg"}`}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function RunSection({ d }: { d: RequestDetail }) {
  const u = d.proposal?.usage;
  const last = d.ai_runs.at(-1);
  if (!u?.provider && !last) return null;
  const live = (u?.provider ?? last?.provider) === "live";
  const rows: [string, ReactNode][] = [
    ["Provider", live ? <span className="font-medium text-accent-strong">Live model · {u?.model ?? last?.model ?? "model not recorded"}</span>
      : <span className="font-medium">Simulated AI: deterministic fixtures, demo mode</span>],
    [live ? "Run time" : "Fixture run time", <>{ms(u?.latency_ms ?? last?.latency_ms)}{!live && <span className="text-fg-subtle"> (not model latency)</span>}</>],
    ["Tokens", live
      ? `${num(u?.input_tokens ?? last?.input_tokens)} input · ${num(u?.output_tokens ?? last?.output_tokens)} output${u?.cache_read_input_tokens ? ` · ${num(u.cache_read_input_tokens)} cache read` : ""}`
      : "None: no model was called"],
    ["Model calls", live ? `${num(u?.api_calls ?? last?.api_calls)} model call(s) · ${num(u?.tool_steps ?? last?.tool_steps)} tool step(s)${u?.retries ? ` · ${u.retries} retr${u.retries === 1 ? "y" : "ies"}` : ""}` : "None"],
  ];
  if (live) rows.push(["Cost", "Not recorded per request (monthly usage is under AI status)"]);
  return (
    <Block title="AI run" testId="activity-run">
      <p className="text-xs text-fg-muted" data-testid="proposal-usage">
        {live
          ? `Produced by ${u?.model ?? last?.model} · ${num(u?.input_tokens)} input / ${num(u?.output_tokens)} output tokens · ${ms(u?.latency_ms)}`
          : `Produced by simulated fixtures · no model tokens · ${ms(u?.latency_ms ?? last?.latency_ms)}`}
      </p>
      <Rows rows={rows} />
      {d.ai_runs.length > 1 && (
        <ol className="mt-1 space-y-0.5 text-xs text-fg-muted" aria-label="All AI runs for this request">
          {d.ai_runs.map((r, i) => (
            <li key={r.id} className={r.error ? "text-danger" : ""}>
              Run {i + 1} · {clock(r.created_at)} · {r.provider === "live" ? `live (${r.model})` : "simulated"} · {humanize(r.status)} · {ms(r.latency_ms)}{r.error ? ` · ${r.error}` : ""}
            </li>
          ))}
        </ol>
      )}
    </Block>
  );
}

function StepsSection({ events }: { events: TimelineEvent[] }) {
  const steps = events.filter((e) => (e.event.startsWith("tool.") && e.tool_name !== "search_knowledge_base") || e.event.startsWith("ai."));
  if (!steps.length) return null;
  return (
    <Block title="Steps and tools" testId="activity-tools">
      <ol className="space-y-1">
        {steps.map((e) => (
          <li key={e.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-xs">
            <span className="min-w-0">
              <span className={`font-medium ${isError(e) ? "text-danger" : "text-fg"}`}>{e.tool_name ? humanize(e.tool_name) : e.event === "ai.classify" ? "Classify request" : e.event === "ai.synthesize" ? "Draft proposal" : humanize(e.event)}</span>
              <span className="block truncate text-fg-subtle" title={brief(e)}>{e.error ?? brief(e)}</span>
            </span>
            <span className="font-mono text-2xs tabular-nums text-fg-subtle">{e.duration_ms != null ? `${e.duration_ms} ms` : ""}</span>
          </li>
        ))}
      </ol>
    </Block>
  );
}

function SourcesSection({ events, cited, onCite }: { events: TimelineEvent[]; cited: Set<string>; onCite: (id: string) => void }) {
  const searches = events.filter((e) => e.tool_name === "search_knowledge_base" && (e.summary as { result?: unknown }).result);
  if (!searches.length) return null;
  return (
    <Block title="Retrieved sources" testId="activity-sources">
      <ol className="space-y-2">
        {searches.map((e) => {
          const s = e.summary as { args: { query: string }; result: { passages: Passage[] } };
          return (
            <li key={e.id} className="text-xs">
              <p className="text-fg-muted">Search “<span className="text-fg">{s.args.query}</span>” · {s.result.passages.length} passage{s.result.passages.length === 1 ? "" : "s"}</p>
              <ul className="mt-0.5 space-y-0.5 pl-3">
                {s.result.passages.map((p) => (
                  <li key={p.chunk_id} className="flex items-baseline gap-2">
                    <button className="min-w-0 truncate text-left text-accent-strong hover:underline" onClick={() => onCite(p.chunk_id)} title={`${p.doc} v${p.version}, ${p.section}`}>
                      {p.doc} v{p.version}, {p.section}
                    </button>
                    {cited.has(p.chunk_id) && <span className="shrink-0 rounded-sm bg-accent-soft px-1 text-2xs font-semibold text-accent-strong">Cited</span>}
                    <span className="ml-auto shrink-0 font-mono text-2xs text-fg-subtle">score {p.score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
    </Block>
  );
}

function ReviewSection({ d }: { d: RequestDetail }) {
  const p = d.proposal;
  const items: { at: string; node: ReactNode; tone?: "warn" | "danger" | "ok" }[] = [
    ...(p?.versions ?? []).map((v) => ({ at: v.created_at, node: <>Proposal version {v.version} by {v.author}{v.edit_note ? ` (“${v.edit_note}”)` : ""}</> })),
    ...d.approvals.map((a) => ({
      at: a.created_at, tone: a.status === "invalidated" ? ("warn" as const) : a.decision === "approved" ? ("ok" as const) : undefined,
      node: <>{a.decision === "approved" ? "Approved" : "Rejected"} by {a.actor}{a.reason ? `: ${a.reason}` : ""}{a.status === "invalidated" ? ` · invalidated (${a.invalidated_reason})` : ""}</>,
    })),
    ...d.executions.map((e) => {
      const t = d.tickets.find((x) => x.id === e.ticket_id);
      return {
        at: e.created_at, tone: e.status === "failed" ? ("danger" as const) : e.status === "succeeded" ? ("ok" as const) : undefined,
        node: <>
          {humanize(e.action_type)} via {e.adapter === "github" ? "GitHub Issues" : "internal tickets"}: {humanize(e.status).toLowerCase()} after {e.attempts} attempt{e.attempts === 1 ? "" : "s"}
          {" · "}{ms(between(e.created_at, e.finished_at))}
          {t && <> · ticket <span className="font-mono">{t.number}</span></>}
          {e.external_url && <> · <a href={e.external_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-medium text-accent-strong underline underline-offset-2">GitHub issue #{e.external_number}<ExternalLink aria-hidden className="size-3" /><span className="sr-only"> (opens in a new tab)</span></a></>}
          {e.last_error && <span className="block text-danger">{e.last_error}</span>}
        </>,
      };
    }),
  ].sort((a, b) => a.at.localeCompare(b.at));
  if (!items.length) return null;
  const dot = { ok: "bg-ok", warn: "bg-[#d48a1c]", danger: "bg-danger" };
  return (
    <Block title="Proposal and approval" testId="activity-review">
      <ol className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="grid grid-cols-[0.5rem_minmax(0,1fr)_auto] items-baseline gap-x-2 text-xs">
            <span aria-hidden className={`size-1.5 translate-y-[-1px] rounded-full ${it.tone ? dot[it.tone] : "bg-line-strong"}`} />
            <span className={`[overflow-wrap:anywhere] ${it.tone === "danger" ? "text-danger" : it.tone === "warn" ? "text-warn" : "text-fg"}`}>{it.node}</span>
            <span className="text-2xs tabular-nums text-fg-subtle">{clock(it.at)}</span>
          </li>
        ))}
      </ol>
    </Block>
  );
}

/** What the backend does not record, so the panel can say so instead of implying it. */
function NotRecorded({ live }: { live: boolean }) {
  const items = [
    "Token usage per step: only per-run totals are stored.",
    live ? "Cost per request: only workspace-level monthly usage is tracked." : "Model latency: the simulated provider calls no model.",
    "Model reasoning: not stored or shown, by design.",
    "Delivery to the customer: ResolveOps never sends replies, so there is no send record.",
  ];
  return (
    <Block title="Not recorded" testId="activity-not-recorded">
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-fg-subtle">{items.map((t) => <li key={t}>{t}</li>)}</ul>
    </Block>
  );
}

export function Activity({ detail: d, onCite }: { detail: RequestDetail; onCite: (id: string) => void }) {
  const events = d.timeline;
  if (!events.length && !d.ai_runs.length) return null;
  const c = d.proposal?.version.content;
  const cited = new Set((c?.citations ?? []).map((x) => x.chunk_id));
  const live = (d.proposal?.usage?.provider ?? d.ai_runs.at(-1)?.provider) === "live";
  const tools = events.filter((e) => e.event === "tool.call").length;
  const sources = new Set(events.filter((e) => e.tool_name === "search_knowledge_base")
    .flatMap((e) => ((e.summary as { result?: { passages: Passage[] } }).result?.passages ?? []).map((p) => p.chunk_id))).size;
  const errors = events.filter(isError);
  const runErrors = d.ai_runs.filter((r) => r.error);
  const errorCount = errors.length + runErrors.filter((r) => !errors.some((e) => e.error === r.error)).length;
  return (
    <details className="group/a rounded-lg ring-1 ring-inset ring-line" data-testid="activity">
      <summary className="flex cursor-pointer select-none flex-wrap items-center gap-x-2 gap-y-1 rounded-lg px-4 py-3 transition-colors hover:bg-canvas">
        <ChevronRight aria-hidden className="size-4 text-fg-subtle transition-transform duration-150 group-open/a:rotate-90" strokeWidth={1.75} />
        <span className="text-ui font-semibold text-fg">Activity</span>
        <span className={`rounded-sm px-1.5 py-px text-2xs font-semibold ${live ? "bg-accent-soft text-accent-strong" : "bg-sunken text-fg-muted"}`} data-testid="activity-mode">
          {live ? "Live model" : "Simulated"}
        </span>
        <span className="ml-auto text-xs tabular-nums text-fg-subtle">
          {tools} tool call{tools === 1 ? "" : "s"} · {sources} source{sources === 1 ? "" : "s"}
          {errorCount ? <span className="text-danger"> · {errorCount} error{errorCount === 1 ? "" : "s"}</span> : null}
          {d.proposal?.usage?.latency_ms != null ? ` · ${ms(d.proposal.usage.latency_ms)}` : ""}
        </span>
      </summary>
      <div data-testid="activity-body">
        <RunSection d={d} />
        {(errors.length > 0 || runErrors.length > 0) && (
          <Block title="Errors" testId="activity-errors">
            <ul className="space-y-1 text-xs text-danger">
              {errors.map((e) => <li key={e.id} className="[overflow-wrap:anywhere]">{clock(e.created_at)} · {e.tool_name ? humanize(e.tool_name) : humanize(e.event)}: {e.error ?? brief(e)}</li>)}
              {runErrors.filter((r) => !errors.some((e) => e.error === r.error)).map((r) => <li key={r.id} className="[overflow-wrap:anywhere]">{clock(r.created_at)} · AI run: {r.error}</li>)}
            </ul>
          </Block>
        )}
        <StepsSection events={events} />
        <SourcesSection events={events} cited={cited} onCite={onCite} />
        <ReviewSection d={d} />
        <NotRecorded live={live} />
        <div className="border-t border-line px-2 py-1">
          <Disclosure title={<span className="text-xs">All recorded events <span className="font-normal tabular-nums text-fg-subtle">{events.length}</span></span>} testId="timeline" className="px-2">
            <EventLog events={events} onCite={onCite} />
          </Disclosure>
        </div>
      </div>
    </details>
  );
}
