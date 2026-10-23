// Unit-level checks for the shared status mapping and approval copy in src/labels.ts.
// Usage: node e2e/labels-check.mjs   (Node ≥ 22.18 / 23.6 runs the .ts module natively by stripping types)
import { approvalCopy, completedTitle, requestStatus } from "../src/labels.ts";

const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`); };

// Approval copy per ticket action type and adapter.
const none = approvalCopy({ type: "none" }, null);
check("none: review reply draft / approve draft, no ticket change",
  none.reviewTitle === "Review reply draft" && none.approveLabel === "Approve draft" && !none.changesTicket
  && /Only records/.test(none.consequence) && /No ticket is created or changed/.test(none.consequence), none.consequence);
const create = approvalCopy({ type: "create_ticket", group: "Support Tier 1", priority: "normal", status: "pending_customer" }, "internal");
check("create_ticket (internal): names the internal ticket, group, priority and status",
  create.approveLabel === "Approve and create ticket" && create.changesTicket
  && create.consequence.includes("an internal ticket for Support Tier 1") && create.consequence.includes("normal priority")
  && create.consequence.includes("waiting on customer") && !/GitHub/.test(create.consequence), create.consequence);
const gh = approvalCopy({ type: "create_ticket", group: "Engineering", priority: "high", status: "open" }, "github");
check("create_ticket (github): names the GitHub issue",
  gh.approveLabel === "Approve and open GitHub issue" && gh.changesTicket && gh.consequence.includes("GitHub repository")
  && gh.reviewTitle.includes("GitHub issue"), gh.consequence);
const note = approvalCopy({ type: "add_note", ticket_id: "3f0e-uuid" }, "internal");
check("add_note: describes adding a note to the existing ticket (no raw id)",
  note.approveLabel === "Approve and add note" && note.changesTicket && note.consequence.includes("Adds an internal note to the customer's existing ticket")
  && !note.consequence.includes("3f0e"), note.consequence);
check("every copy says nothing is sent to the customer",
  [none, create, gh, note].every((c) => c.consequence.includes("nothing is sent to the customer") || c.consequence.includes("Nothing is sent to the customer")));

// Completed titles come from what actually executed.
check("completed titles reflect the executed action",
  completedTitle("none", []) === "Reply draft approved"
  && completedTitle("create_ticket", [{ number: "NS-1001" }]) === "Ticket NS-1001 created"
  && completedTitle("create_ticket", [{ number: "GH-7", external_number: 7 }]) === "GitHub issue #7 opened"
  && completedTitle("add_note", [{ number: "NS-903" }]) === "Note added to ticket NS-903"
  && completedTitle("add_note", [], "Ticket NS-903 updated") === "Ticket NS-903 updated");

// Status mapping: actual state + next action only.
const st = (state, next_action = null, extra = {}) => requestStatus({ state, is_template: false, next_action, ...extra });
check("template → Not processed (ready)", requestStatus({ state: "received", is_template: true }).label === "Not processed"
  && requestStatus({ state: "received", is_template: true }).key === "ready");
check("received → Ready to process", st("received").label === "Ready to process");
check("in-flight states → Processing", ["classified", "context_resolved", "retrieved", "approved", "executing"].every((s) => st(s).key === "processing"));
check("awaiting review + clarify → Needs information (awaiting review)",
  st("awaiting_review", "clarify").label === "Needs information" && st("awaiting_review", "clarify").detail === "Awaiting review");
check("awaiting review + resolve/escalate → Awaiting review",
  st("awaiting_review", "resolve").label === "Awaiting review" && st("awaiting_review", "escalate").label === "Awaiting review");
check("completed + clarify → Needs information (approved)", st("completed", "clarify").key === "needs_info"
  && st("completed", null, { resolution: "clarification_requested" }).key === "needs_info");
check("completed + resolve → Completed", st("completed", "resolve").label === "Completed");
check("rejected / failed / error / stale / unsupported map 1:1",
  st("rejected").key === "rejected" && st("failed").key === "failed" && st("error").key === "error"
  && st("stale").key === "stale" && st("unsupported").key === "unsupported");

const failed = results.filter((r) => !r).length;
console.log(`\n${results.length - failed}/${results.length} label checks passed`);
process.exit(failed ? 1 : 0);
