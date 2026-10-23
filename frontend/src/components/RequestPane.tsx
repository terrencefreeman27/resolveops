import { useState } from "react";
import { Building2, Check, PanelRight, Pencil, Play, RefreshCw, RotateCcw, Ticket, X } from "lucide-react";
import type { RequestDetail } from "../api";
import { categoryLabel, humanize } from "../labels";
import { ProposalEditor } from "./ProposalEditor";
import { AttentionList, NEXT_ACTION, TicketActionView, UsageLine, approvalConsequence, versionNote } from "./ProposalParts";
import { Timeline } from "./Timeline";
import { Button, HelpTip, StateBadge, timeAgo } from "./ui";

export { versionNote };

function Callout({ tone, title, children, testId, role = "status" }: {
  tone: "warn" | "danger" | "neutral" | "ok"; title: string; children: React.ReactNode; testId?: string; role?: string;
}) {
  const t = { warn: "bg-warn-soft text-warn ring-warn-line", danger: "bg-danger-soft text-danger ring-danger-line", neutral: "bg-sunken text-fg-muted ring-line", ok: "bg-ok-soft text-ok ring-[#cfe6d6]" }[tone];
  return (
    <div className={`rounded-lg px-4 py-3 text-ui ring-1 ring-inset ${t}`} role={role} data-testid={testId}>
      <p className="font-semibold">{title}</p>
      <div className="mt-1 space-y-1 text-fg-muted">{children}</div>
    </div>
  );
}

export function RequestPane(props: {
  detail: RequestDetail;
  groups: string[];
  busy: boolean;
  busyAction: string | null;
  onRun: () => void;
  onEdit: (changes: object) => Promise<boolean>;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onRetry: () => void;
  onEscalateInternal: () => void;
  onCite: (chunkId: string) => void;
  onOpenDetails?: () => void;
}) {
  const { detail: d, groups, busy, busyAction } = props;
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const p = d.proposal;
  const c = p?.version.content;
  const can = d.allowed_actions;
  const invalidated = d.approvals.filter((a) => a.status === "invalidated").length;
  const hasActions = !!p && !editing && (can.approve || can.edit || can.reject || can.retry || can.escalate_internal);
  const next = c ? NEXT_ACTION[c.next_action] : null;
  const meta = [d.category && categoryLabel(d.category), d.priority && `${humanize(d.priority)} priority`, d.resolution && `Outcome: ${humanize(d.resolution)}`].filter(Boolean);

  return (
    <section className="flex h-full min-h-0 flex-col bg-surface" data-testid="request-pane" aria-label="Request">
      <div className="pane-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[46rem] space-y-6 px-5 pb-10 pt-5 sm:px-8">
          {/* 1. Title and essential status */}
          <header className="space-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <StateBadge state={d.state} template={d.is_template} />
              {meta.length > 0 && <span className="text-xs text-fg-subtle">{meta.join(" · ")}</span>}
              {props.onOpenDetails && (
                <span className="ml-auto hidden lg:block xl:hidden">
                  <Button size="sm" variant="ghost" icon={PanelRight} onClick={props.onOpenDetails} data-testid="open-details">Details</Button>
                </span>
              )}
            </div>
            <h1 className="text-xl font-semibold leading-snug tracking-tight text-fg [overflow-wrap:anywhere] [text-wrap:balance]">{d.subject}</h1>
            <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-ui text-fg-muted">
              <Building2 aria-hidden className="size-3.5 shrink-0 text-fg-subtle" strokeWidth={1.75} />
              <span className="font-medium text-fg [overflow-wrap:anywhere]">{d.customer?.company_name ?? d.from_name}</span>
              <span aria-hidden className="text-fg-subtle">·</span>
              <span className="[overflow-wrap:anywhere]">{d.from_name} <span className="text-fg-subtle">&lt;{d.from_email}&gt;</span></span>
              <span aria-hidden className="text-fg-subtle">·</span>
              <span className="text-fg-subtle">{timeAgo(d.received_at)}</span>
              {d.customer?.is_synthetic && <span className="rounded-sm bg-sunken px-1.5 py-px text-2xs font-medium text-fg-muted">Synthetic customer</span>}
            </p>
          </header>

          {/* 2. Customer message */}
          <section aria-label="Written by the customer">
            <div className="whitespace-pre-wrap rounded-lg bg-canvas px-4 py-3 text-md text-fg [overflow-wrap:anywhere] ring-1 ring-inset ring-line">{d.body}</div>
          </section>

          {d.is_template && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg px-4 py-3 ring-1 ring-inset ring-accent-line">
              <p className="text-ui text-fg-muted"><span className="font-medium text-fg">Seeded example.</span> Running the workflow makes your own copy; the shared example is unchanged.</p>
              <Button variant="primary" icon={Play} onClick={props.onRun} loading={busyAction === "run"} disabled={busy} data-testid="run-workflow">Run workflow</Button>
            </div>
          )}

          {d.state === "completed" && (
            <Callout tone="ok" title={d.tickets.length ? `Completed · ticket ${d.tickets.map((t) => t.number).join(", ")} recorded` : "Completed · reply draft recorded, no ticket change"} testId="completed-banner">
              <p>The approved version was executed{d.executions.at(-1) ? ` via the ${d.executions.at(-1)!.adapter} adapter` : ""}. The reply draft is recorded for sending by your team; nothing was sent automatically.</p>
            </Callout>
          )}

          {d.state === "stale" && (
            <Callout tone="warn" title={`Stale: version ${p?.version.version} relied on documentation or rules that have changed`} testId="stale-banner">
              <p>{p?.stale_reason ?? d.state_reason}</p>
              <p>It can't be approved or executed. Reprocessing re-runs the workflow against current documents and rules and adds a new version for review.</p>
              {!d.is_template && can.run && <Button className="mt-1.5" variant="primary" icon={RefreshCw} onClick={props.onRun} loading={busyAction === "run"} disabled={busy} data-testid="reprocess">Reprocess with current documentation</Button>}
            </Callout>
          )}

          {d.state_reason && ["unsupported", "error", "failed", "rejected"].includes(d.state) && (
            <Callout tone={d.state === "rejected" || d.state === "unsupported" ? "neutral" : "danger"}
              title={d.state === "unsupported" ? "Not processed" : d.state === "rejected" ? "Rejected"
                : d.state === "error" && d.ai_runs.at(-1)?.provider === "live" ? "Live provider error (no simulated output was used)" : "Problem"}>
              <p>{d.state_reason}</p>
              {!d.is_template && can.run && <Button className="mt-1.5" icon={RotateCcw} onClick={props.onRun} loading={busyAction === "run"} disabled={busy}>Reprocess</Button>}
            </Callout>
          )}

          {p && c && next && (
            <article className="space-y-6" data-testid="proposal" aria-label="Proposal">
              {/* 3. Proposed next step */}
              <section className="rounded-lg ring-1 ring-inset ring-line">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-2.5">
                  <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-ui font-semibold ${next.tone}`}>
                    <next.icon aria-hidden className="size-4" strokeWidth={2} /><span>{next.label}</span>
                  </span>
                  <span className="text-xs font-medium text-fg-subtle">Proposed next step</span>
                  <span className="ml-auto flex items-center gap-2 text-xs text-fg-subtle">
                    <span data-testid="proposal-version" className="tabular-nums">Version {p.version.version} of {p.versions.length}</span>
                    <span className={`rounded-sm px-1.5 py-0.5 text-2xs font-semibold ${c.simulated ? "bg-fg text-white" : "bg-accent text-white"}`} data-testid="provider-label">{c.provider_label}</span>
                  </span>
                </div>
                <div className="space-y-2 px-4 py-3">
                  <p className="text-md font-medium leading-snug text-fg">{c.summary}</p>
                  <p className="text-ui text-fg-muted">{c.justification}</p>
                  <UsageLine u={p.usage} />
                </div>
              </section>

              <AttentionList c={c} onCite={props.onCite} pending={d.state === "awaiting_review"} />

              {editing ? (
                <ProposalEditor content={c} groups={groups} busy={busy} onCancel={() => setEditing(false)}
                  onSave={async (changes) => { if (await props.onEdit(changes)) setEditing(false); }} />
              ) : (
                <>
                  {/* 4. Editable draft reply */}
                  <section aria-labelledby="draft-h">
                    <div className="flex items-center gap-2 pb-2">
                      <h2 id="draft-h" className="text-ui font-semibold text-fg">Draft reply</h2>
                      <HelpTip label="About the draft reply">The draft is never sent automatically. Approving records the reviewed draft; editing saves a new version that needs its own approval.</HelpTip>
                      {can.edit && <Button size="sm" variant="ghost" icon={Pencil} className="ml-auto" onClick={() => setEditing(true)} disabled={busy} data-testid="edit">Edit</Button>}
                    </div>
                    <div className="whitespace-pre-wrap rounded-lg px-4 py-3 text-md text-fg [overflow-wrap:anywhere] ring-1 ring-inset ring-line" data-testid="draft-reply">{c.draft_reply}</div>
                    {c.citations.length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Citations in this draft">
                        {c.citations.map((ct, i) => {
                          const note = versionNote(p.citation_versions?.[ct.document_version_id], ct.version);
                          return (
                            <button key={ct.chunk_id} onClick={() => props.onCite(ct.chunk_id)} title={`${ct.doc_title}, ${ct.section}: ${ct.claim}`}
                              className={`inline-flex max-w-full items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs transition-colors ${note ? "bg-warn-soft text-warn hover:bg-warn-line/50" : "bg-accent-soft text-accent-strong hover:bg-accent-line/60"}`}>
                              <span className="font-semibold tabular-nums">{i + 1}</span>
                              <span className="truncate">{ct.section}{note}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </section>

                  <section aria-labelledby="ticket-h">
                    <div className="flex items-center gap-2 pb-2">
                      <Ticket aria-hidden className="size-4 text-fg-subtle" strokeWidth={1.75} />
                      <h2 id="ticket-h" className="text-ui font-semibold text-fg">Ticket action</h2>
                    </div>
                    <div className="rounded-lg px-4 py-3 ring-1 ring-inset ring-line"><TicketActionView ta={c.ticket_action} /></div>
                  </section>
                </>
              )}

              {invalidated > 0 && d.state === "awaiting_review" && (
                <p className="text-ui text-warn">This proposal was edited after an earlier approval. The old approval is no longer valid; version {p.version.version} needs its own approval.</p>
              )}
            </article>
          )}

          {/* 5. Execution details */}
          {d.timeline.length > 0 && <Timeline events={d.timeline} onCite={props.onCite} />}
        </div>
      </div>

      {hasActions && p && c && (
        <footer className="shrink-0 border-t border-line bg-surface/95 px-5 py-3 sm:px-8" aria-label="Review actions" data-testid="approval-bar">
          {rejecting ? (
            <form className="mx-auto flex max-w-[46rem] flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) props.onReject(reason.trim()); }}>
              <label className="sr-only" htmlFor="reject-reason">Rejection reason</label>
              <input id="reject-reason" autoFocus className="h-8 min-w-0 flex-1 basis-56 rounded-md border-0 bg-surface px-2.5 text-ui ring-1 ring-inset ring-line-strong placeholder:text-fg-subtle"
                placeholder="Why are you rejecting this proposal?" value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button variant="danger" type="submit" loading={busyAction === "reject"} disabled={busy || !reason.trim()}>Confirm reject</Button>
              <Button variant="ghost" type="button" onClick={() => setRejecting(false)}>Cancel</Button>
            </form>
          ) : (
            <div className="mx-auto flex max-w-[46rem] flex-wrap items-center gap-x-4 gap-y-2">
              <p className="min-w-0 flex-1 basis-60 text-xs leading-snug text-fg-muted">
                {can.approve ? <>{approvalConsequence(c.ticket_action)} <span className="text-fg-subtle">Nothing is sent to the customer.</span></>
                  : can.retry ? "The ticket action did not complete. Retrying is safe: it reuses the same idempotency key."
                  : "Review the proposal."}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {can.reject && <Button variant="ghost" icon={X} onClick={() => setRejecting(true)} disabled={busy} className="text-danger hover:bg-danger-soft hover:text-danger">Reject</Button>}
                {can.escalate_internal && <Button onClick={props.onEscalateInternal} loading={busyAction === "escalate"} disabled={busy} data-testid="escalate-internal"
                  title="Create an internal ticket instead. Refused if GitHub already has an issue for this execution.">Use internal ticket instead</Button>}
                {can.retry && <Button variant="primary" icon={RotateCcw} onClick={props.onRetry} loading={busyAction === "retry"} disabled={busy} data-testid="retry">Retry execution</Button>}
                {can.approve && <Button variant="primary" icon={Check} onClick={props.onApprove} loading={busyAction === "approve"} disabled={busy} data-testid="approve">Approve version {p.version.version}</Button>}
              </div>
            </div>
          )}
        </footer>
      )}
    </section>
  );
}
