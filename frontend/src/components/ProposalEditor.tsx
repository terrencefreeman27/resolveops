import { useState } from "react";
import type { ProposalContent, TicketAction } from "../api";
import { Button } from "./ui";

const field = "w-full rounded-md border-0 bg-white px-2.5 py-1.5 text-sm text-zinc-900 ring-1 ring-inset ring-zinc-300";

export function ProposalEditor(props: {
  content: ProposalContent;
  groups: string[];
  busy: boolean;
  onCancel: () => void;
  onSave: (changes: { draft_reply?: string; next_action?: string; ticket_action?: TicketAction; note?: string }) => void;
}) {
  const { content, groups, busy, onCancel, onSave } = props;
  const [reply, setReply] = useState(content.draft_reply);
  const [nextAction, setNextAction] = useState(content.next_action);
  const [ta, setTa] = useState<TicketAction>(content.ticket_action);
  const [note, setNote] = useState("");
  const isCreate = ta.type === "create_ticket";

  function save() {
    const changes: Parameters<typeof onSave>[0] = {};
    if (reply !== content.draft_reply) changes.draft_reply = reply;
    if (nextAction !== content.next_action) changes.next_action = nextAction;
    if (JSON.stringify(ta) !== JSON.stringify(content.ticket_action)) changes.ticket_action = ta;
    if (note) changes.note = note;
    onSave(changes);
  }

  return (
    <div className="space-y-4 rounded-lg border border-amber-200 bg-amber-50/40 p-4" data-testid="proposal-editor">
      <p className="text-sm text-amber-900">Saving creates a new proposal version. Any earlier approval stops being valid.</p>
      <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
        Draft reply
        <textarea className={`${field} min-h-56 font-normal leading-relaxed`} value={reply} onChange={(e) => setReply(e.target.value)} maxLength={4000} />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
          Next action
          <select className={field} value={nextAction} onChange={(e) => setNextAction(e.target.value as ProposalContent["next_action"])}>
            <option value="resolve">Resolve</option>
            <option value="clarify">Ask for clarification</option>
            <option value="escalate">Escalate</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
          Ticket action
          <select className={field} value={ta.type} onChange={(e) => {
            const type = e.target.value as TicketAction["type"];
            setTa(type === "create_ticket"
              ? { type, subject: ta.subject ?? content.summary.slice(0, 150), body: ta.body ?? content.summary, priority: ta.priority ?? "normal", group: ta.group ?? groups[0], status: ta.status ?? "open" }
              : type === content.ticket_action.type ? content.ticket_action : { type });
          }}>
            <option value="none">No ticket change</option>
            <option value="create_ticket">Create ticket</option>
            {content.ticket_action.type === "add_note" && <option value="add_note">Add note to existing ticket</option>}
          </select>
        </label>
      </div>
      {isCreate && (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1.5 text-sm font-medium text-zinc-700 sm:col-span-3">
            Ticket subject
            <input className={field} value={ta.subject ?? ""} maxLength={200} onChange={(e) => setTa({ ...ta, subject: e.target.value })} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
            Group
            <select className={field} value={ta.group ?? ""} onChange={(e) => setTa({ ...ta, group: e.target.value })}>
              {groups.map((g) => <option key={g}>{g}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
            Priority
            <select className={field} value={ta.priority ?? "normal"} onChange={(e) => setTa({ ...ta, priority: e.target.value as TicketAction["priority"] })}>
              {["low", "normal", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
            Status
            <select className={field} value={ta.status ?? "open"} onChange={(e) => setTa({ ...ta, status: e.target.value as TicketAction["status"] })}>
              {["open", "pending_customer", "solved"].map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-zinc-700 sm:col-span-3">
            Ticket body
            <textarea className={`${field} min-h-20 font-normal`} value={ta.body ?? ""} maxLength={4000} onChange={(e) => setTa({ ...ta, body: e.target.value })} />
          </label>
        </div>
      )}
      <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
        Edit note (optional)
        <input className={field} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Why you changed it" />
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button variant="primary" onClick={save} disabled={busy}>Save as new version</Button>
      </div>
    </div>
  );
}
