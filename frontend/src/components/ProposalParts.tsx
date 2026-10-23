import { ArrowUpRight, CircleAlert, MessageCircleQuestion, MessageSquareReply, type LucideIcon } from "lucide-react";
import type { CitationVersion, ProposalContent, TicketAction } from "../api";
import { humanize } from "../labels";
import { Disclosure } from "./ui";

export const NEXT_ACTION: Record<ProposalContent["next_action"], { label: string; icon: LucideIcon; tone: string }> = {
  resolve: { label: "Resolve with reply", icon: MessageSquareReply, tone: "bg-accent-soft text-accent-strong" },
  clarify: { label: "Ask for clarification", icon: MessageCircleQuestion, tone: "bg-warn-soft text-warn" },
  escalate: { label: "Escalate", icon: ArrowUpRight, tone: "bg-danger-soft text-danger" },
};

/** Heading for the ticket part of a proposal, named for what it would actually do. */
export function ticketActionTitle(ta: TicketAction, adapter: string | null | undefined): string {
  if (ta.type === "create_ticket") return adapter === "github" ? "New GitHub issue" : "New internal ticket";
  if (ta.type === "add_note") return "Note on the existing ticket";
  return "Ticket: no change";
}

export function TicketActionView({ ta, adapter }: { ta: TicketAction; adapter?: string | null }) {
  if (ta.type === "none") return <p className="text-ui text-fg-muted">No ticket is created or changed. Approval records the reviewed reply draft only.</p>;
  if (ta.type === "add_note") return <p className="text-ui text-fg-muted [overflow-wrap:anywhere]">Internal note added to the customer's existing ticket: <span className="text-fg">{ta.body}</span></p>;
  return (
    <div className="space-y-2">
      <p className="text-ui font-medium text-fg [overflow-wrap:anywhere]">{ta.subject}</p>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <div className="flex gap-1.5"><dt className="text-fg-subtle">Destination</dt><dd className="font-medium text-fg">{adapter === "github" ? "GitHub Issues" : "Internal tickets"}</dd></div>
        <div className="flex gap-1.5"><dt className="text-fg-subtle">Group</dt><dd className="font-medium text-fg">{ta.group}</dd></div>
        <div className="flex gap-1.5"><dt className="text-fg-subtle">Priority</dt><dd className="font-medium text-fg">{humanize(ta.priority)}</dd></div>
        <div className="flex gap-1.5"><dt className="text-fg-subtle">Status</dt><dd className="font-medium text-fg">{humanize(ta.status)}</dd></div>
      </dl>
      {ta.body && <p className="text-xs leading-relaxed text-fg-muted [overflow-wrap:anywhere]">{ta.body}</p>}
    </div>
  );
}

export function versionNote(cv: CitationVersion | undefined, v: number) {
  if (!cv || cv.status === "active") return "";
  if (cv.document_status === "deleted") return ` · v${v}, deleted`;
  return cv.current_version ? ` · v${v}, superseded by v${cv.current_version}` : ` · v${v}, ${cv.status}`;
}

/** Everything a reviewer must weigh before approving: evidence problems, risk flags, rules, missing info. */
export function AttentionList({ c, onCite, pending = true }: { c: ProposalContent; onCite: (id: string) => void; pending?: boolean }) {
  const ev = c.evidence_check && c.evidence_check.status !== "sufficient" ? c.evidence_check : null;
  const any = ev || c.risk_flags.length || c.rule_hits.length || c.escalation_reason || c.missing_info.length;
  if (!any) return null;
  const item = "flex gap-2.5 py-2.5 first:pt-0 last:pb-0";
  return (
    <section aria-labelledby="attention-h" className="rounded-lg bg-warn-soft/60 px-4 py-3 ring-1 ring-inset ring-warn-line">
      <h3 id="attention-h" className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-warn">
        <CircleAlert aria-hidden className="size-3.5" strokeWidth={2} />{pending ? "Before you approve" : "Review notes"}
      </h3>
      <ul className="divide-y divide-warn-line/70 text-ui text-fg">
        {ev && (
          <li className={item} data-testid="evidence-check" data-status={ev.status}>
            <div className="min-w-0 flex-1 space-y-1">
              <p className="font-medium">Evidence check: {ev.status === "conflicting" ? "documents conflict" : "not enough documentation"}</p>
              {ev.status === "insufficient" && <p className="text-fg-muted">No passage was relevant enough to support a resolution.</p>}
              {ev.conflicts.map((x) => (
                <ul key={x.key} className="space-y-0.5 text-fg-muted">{x.values.map((v) => (
                  <li key={v.chunk_id}>
                    <button className="font-medium text-accent-strong underline decoration-accent-line underline-offset-2 hover:decoration-accent" onClick={() => onCite(v.chunk_id)}>{v.doc_title} v{v.version}, {v.section}</button>
                    : {humanize(x.key)} = {v.value}
                  </li>
                ))}</ul>
              ))}
              {ev.effect && <p className="font-medium">{ev.effect}</p>}
              <Disclosure title="How this was checked" className="text-xs">
                <p className="pb-1 pl-6 text-xs text-fg-muted">
                  Checked by application code, not by the model. A proposal with unsupported evidence can be clarified or escalated, never resolved.
                  {ev.status === "insufficient" && <> Relevance threshold {ev.threshold.toFixed(2)}; best passage {ev.best_score?.toFixed(2) ?? "none"}.</>}
                </p>
              </Disclosure>
            </div>
          </li>
        )}
        {c.risk_flags.length > 0 && (
          <li className={item}><div><p className="font-medium">Risk flags</p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-fg-muted">{c.risk_flags.map((f) => <li key={f}>{f}</li>)}</ul></div></li>
        )}
        {c.rule_hits.map((h) => (
          <li key={h.key} className={item}><div><p className="font-medium">Policy rule: {h.name}</p><p className="text-fg-muted">{h.effect}</p></div></li>
        ))}
        {c.escalation_reason && <li className={item}><div><p className="font-medium">Why escalate</p><p className="text-fg-muted">{c.escalation_reason}</p></div></li>}
        {c.missing_info.length > 0 && (
          <li className={item}><div><p className="font-medium">Missing information</p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-fg-muted">{c.missing_info.map((m) => <li key={m}>{m}</li>)}</ul></div></li>
        )}
      </ul>
    </section>
  );
}
