import { useState } from "react";
import type { ProposalContent, RequestDetail, TicketAction } from "../api";
import { categoryLabel } from "./Inbox";
import { ProposalEditor } from "./ProposalEditor";
import { Timeline } from "./Timeline";
import { Button, PanelHeading, StateBadge, Tag, timeAgo } from "./ui";

const NEXT_ACTION: Record<ProposalContent["next_action"], { label: string; tone: "teal" | "amber" | "red" }> = {
  resolve: { label: "Resolve with reply", tone: "teal" },
  clarify: { label: "Ask for clarification", tone: "amber" },
  escalate: { label: "Escalate", tone: "red" },
};

function TicketActionView({ ta }: { ta: TicketAction }) {
  if (ta.type === "none") return <p className="text-sm text-zinc-600">No ticket change. Approval records the reviewed reply draft only.</p>;
  if (ta.type === "add_note") return <p className="text-sm text-zinc-700">Add note to existing ticket: <span className="text-zinc-900">{ta.body}</span></p>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-zinc-500">Create</dt><dd className="font-medium text-zinc-900">{ta.subject}</dd>
      <dt className="text-zinc-500">Group</dt><dd>{ta.group}</dd>
      <dt className="text-zinc-500">Priority</dt><dd>{ta.priority}</dd>
      <dt className="text-zinc-500">Status</dt><dd>{ta.status?.replace("_", " ")}</dd>
      <dt className="text-zinc-500">Body</dt><dd className="text-zinc-700">{ta.body}</dd>
    </dl>
  );
}

export function RequestPane(props: {
  detail: RequestDetail;
  groups: string[];
  busy: boolean;
  onRun: () => void;
  onEdit: (changes: object) => Promise<boolean>;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onRetry: () => void;
  onCite: (chunkId: string) => void;
}) {
  const { detail: d, groups, busy } = props;
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const p = d.proposal;
  const c = p?.version.content;
  const can = d.allowed_actions;
  const invalidated = d.approvals.filter((a) => a.status === "invalidated").length;

  return (
    <section className="min-h-0 overflow-y-auto bg-white" data-testid="request-pane">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-5">
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StateBadge state={d.state} template={d.is_template} />
            {d.category && <Tag>{categoryLabel(d.category)}</Tag>}
            {d.priority && <Tag tone={d.priority === "high" || d.priority === "urgent" ? "red" : "zinc"}>Priority {d.priority}</Tag>}
            {d.resolution && <Tag tone="teal">Outcome: {d.resolution.replace("_", " ")}</Tag>}
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">{d.subject}</h1>
          <p className="text-sm text-zinc-600">
            {d.from_name} &lt;{d.from_email}&gt; at {d.customer?.company_name}
            {d.customer?.is_synthetic && <span className="ml-1.5"><Tag>Synthetic customer</Tag></span>}
            <span className="ml-1.5 text-zinc-400">{timeAgo(d.received_at)}</span>
          </p>
        </header>

        <blockquote className="whitespace-pre-wrap rounded-lg bg-zinc-50 px-4 py-3 text-[15px] leading-relaxed text-zinc-800 ring-1 ring-inset ring-zinc-200">
          {d.body}
        </blockquote>

        {d.is_template && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-zinc-300 px-4 py-3">
            <p className="text-sm text-zinc-600">Seeded requests are shared. Running the workflow makes your own copy.</p>
            <Button variant="primary" onClick={props.onRun} disabled={busy} data-testid="run-workflow">Run workflow</Button>
          </div>
        )}

        {d.state_reason && ["unsupported", "error", "failed", "rejected", "stale"].includes(d.state) && (
          <div className={`rounded-lg px-4 py-3 text-sm ${d.state === "rejected" ? "bg-zinc-100 text-zinc-700" : "bg-red-50 text-red-800"}`} role="status">
            <p className="font-medium">{d.state === "unsupported" ? "Not processed" : d.state === "rejected" ? "Rejected" : "Problem"}</p>
            <p className="mt-0.5">{d.state_reason}</p>
            {!d.is_template && can.run && <Button className="mt-2" onClick={props.onRun} disabled={busy}>Reprocess</Button>}
          </div>
        )}

        {p && c && (
          <article className="space-y-5" data-testid="proposal">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-zinc-900">Proposed resolution</h2>
                <Tag tone={NEXT_ACTION[c.next_action].tone}>{NEXT_ACTION[c.next_action].label}</Tag>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <span data-testid="proposal-version">Version {p.version.version} of {p.versions.length}</span>
                <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 font-medium text-white">{c.provider_label}</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-sm text-zinc-900">{c.summary}</p>
              <p className="text-sm text-zinc-600"><span className="font-medium text-zinc-700">{categoryLabel(c.category)}, {c.priority} priority.</span> {c.justification}</p>
            </div>

            {c.risk_flags.length > 0 && (
              <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
                <p className="font-medium">Risk flags</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5">{c.risk_flags.map((f) => <li key={f}>{f}</li>)}</ul>
              </div>
            )}
            {(c.rule_hits.length > 0 || c.escalation_reason || c.missing_info.length > 0) && (
              <dl className="grid gap-2 text-sm">
                {c.rule_hits.map((h) => (
                  <div key={h.key} className="flex flex-wrap gap-x-2"><dt className="font-medium text-zinc-700">Policy rule: {h.name}</dt><dd className="text-zinc-600">{h.effect}</dd></div>
                ))}
                {c.escalation_reason && <div className="flex flex-wrap gap-x-2"><dt className="font-medium text-zinc-700">Escalation reason</dt><dd className="text-zinc-600">{c.escalation_reason}</dd></div>}
                {c.missing_info.length > 0 && (
                  <div><dt className="font-medium text-zinc-700">Missing information</dt>
                    <dd><ul className="list-disc pl-5 text-zinc-600">{c.missing_info.map((m) => <li key={m}>{m}</li>)}</ul></dd></div>
                )}
              </dl>
            )}

            {editing ? (
              <ProposalEditor content={c} groups={groups} busy={busy} onCancel={() => setEditing(false)}
                onSave={async (changes) => { if (await props.onEdit(changes)) setEditing(false); }} />
            ) : (
              <>
                <div>
                  <PanelHeading aside={<span className="text-xs text-zinc-500">Draft only, never sent automatically</span>}>Draft reply</PanelHeading>
                  <div className="whitespace-pre-wrap rounded-lg px-4 py-3 text-[15px] leading-relaxed text-zinc-800 ring-1 ring-inset ring-zinc-200" data-testid="draft-reply">{c.draft_reply}</div>
                  {c.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {c.citations.map((ct, i) => (
                        <button key={ct.chunk_id} onClick={() => props.onCite(ct.chunk_id)} title={ct.claim}
                          className="rounded-md bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800 hover:bg-teal-100">
                          [{i + 1}] {ct.doc_title}, {ct.section}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <PanelHeading>Proposed ticket action</PanelHeading>
                  <div className="rounded-lg px-4 py-3 ring-1 ring-inset ring-zinc-200"><TicketActionView ta={c.ticket_action} /></div>
                </div>
              </>
            )}

            {invalidated > 0 && d.state === "awaiting_review" && (
              <p className="text-sm text-amber-800">This proposal was edited after an earlier approval. The old approval is no longer valid; version {p.version.version} needs its own approval.</p>
            )}

            {!editing && (can.approve || can.edit || can.reject || can.retry) && (
              <div className="sticky bottom-0 -mx-6 flex flex-wrap items-center gap-2 border-t border-zinc-200 bg-white/95 px-6 py-3 backdrop-blur">
                {can.approve && <Button variant="primary" onClick={props.onApprove} disabled={busy} data-testid="approve">Approve version {p.version.version}</Button>}
                {can.retry && <Button variant="primary" onClick={props.onRetry} disabled={busy} data-testid="retry">Retry execution</Button>}
                {can.edit && <Button onClick={() => setEditing(true)} disabled={busy} data-testid="edit">Edit</Button>}
                {can.reject && !rejecting && <Button variant="danger" onClick={() => setRejecting(true)} disabled={busy}>Reject</Button>}
                {rejecting && (
                  <form className="flex flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) props.onReject(reason.trim()); }}>
                    <label className="sr-only" htmlFor="reject-reason">Rejection reason</label>
                    <input id="reject-reason" autoFocus className="min-w-0 flex-1 rounded-md border-0 px-2.5 py-1.5 text-sm ring-1 ring-inset ring-zinc-300" placeholder="Reason for rejecting" value={reason} onChange={(e) => setReason(e.target.value)} />
                    <Button variant="danger" type="submit" disabled={busy || !reason.trim()}>Confirm reject</Button>
                    <Button variant="ghost" type="button" onClick={() => setRejecting(false)}>Cancel</Button>
                  </form>
                )}
              </div>
            )}
          </article>
        )}

        {d.timeline.length > 0 && <Timeline events={d.timeline} onCite={props.onCite} />}
      </div>
    </section>
  );
}
