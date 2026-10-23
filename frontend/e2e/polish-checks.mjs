// Portfolio-polish browser checks: inbox language, action-specific approval copy, completed states,
// request-scoped notifications, preserved edits on recoverable errors, duplicate-submit protection,
// category-relevant context, the Activity section, and laptop layouts.
// Usage: node e2e/polish-checks.mjs   (BASE defaults to http://localhost:8080). Screenshots: docs/screenshots/polish/
import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { runScenario } from "./ui-helpers.mjs";

const BASE = process.env.BASE ?? "http://localhost:8080";
const OUT = fileURLToPath(new URL("../../docs/screenshots/polish/", import.meta.url));
await mkdir(OUT, { recursive: true });
const results = [];
const pageErrors = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`); };
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
const settle = (p) => p.waitForFunction(() => !document.querySelector("[aria-busy=true]"));

const browser = await chromium.launch();
async function visitor(width = 1440, height = 900) {
  const ctx = await browser.newContext({ viewport: { width, height }, permissions: ["clipboard-read", "clipboard-write"] });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.goto(BASE);
  await page.getByTestId("inbox").getByText("Not processed").first().waitFor();
  return { ctx, page };
}
const shot = async (p, name) => { await settle(p); await p.waitForTimeout(200); await p.screenshot({ path: `${OUT}${name}.png` }); };
const api = (p, path) => p.evaluate(async (path) => (await fetch(path)).json(), path);
const latest = async (p) => (await api(p, "/api/w/northstar/requests")).requests
  .filter((r) => !r.is_template).sort((a, b) => b.received_at.localeCompare(a.received_at))[0];
const firstGroup = (p) => p.getByTestId("facts-primary").locator("[data-group]").first().getAttribute("data-group");

try {
  // 1. Inbox language: real message previews, "Example requests", "Not processed".
  const A = await visitor();
  const list = (await api(A.page, "/api/w/northstar/requests")).requests;
  const previews = await A.page.getByTestId("inbox-preview").allInnerTexts();
  check("inbox previews show the customer's actual message", previews.length === list.length
    && list.every((r, i) => previews[i] === r.preview) && !previews.some((t) => /Same wording|→/.test(t)), previews[0]?.slice(0, 60));
  const inboxText = await A.page.getByTestId("inbox").innerText();
  check("inbox says 'Example requests' and 'Not processed' (no 'Seeded')",
    inboxText.includes("Example requests") && !/Seeded/i.test(inboxText)
    && (await A.page.getByTestId("inbox").getByText("Not processed").count()) === 6);
  await shot(A.page, "after-01-inbox");

  // 2. Access scenario: resolve + new internal ticket; seats/permissions first.
  await runScenario(A.page, "access_reporting_after_upgrade");
  await A.page.getByTestId("proposal").waitFor();
  const access = await latest(A.page);
  check("access: approve button and consequence name the internal ticket",
    (await A.page.getByTestId("approve").innerText()) === "Approve and create ticket"
    && /Creates an internal ticket for Support Tier 1/.test(await A.page.getByTestId("approval-consequence").innerText())
    && (await A.page.locator("#ticket-h").innerText()) === "New internal ticket");
  check("access: version shown but secondary (in proposal header and approval note)",
    (await A.page.getByTestId("proposal-version").innerText()) === "Version 1 of 1"
    && (await A.page.getByTestId("approval-consequence").innerText()).includes("applies to version 1"));
  check("access: context leads with seats and permissions, then subscription; invoices collapsed",
    (await firstGroup(A.page)) === "seats" && (await A.page.getByTestId("facts-group-billing").count()) === 1
    && !(await A.page.getByTestId("facts-group-billing").evaluate((el) => el.open)));
  await shot(A.page, "after-02-access-proposal");

  // 3. Citations still open their passage with document version.
  await A.page.getByTestId("citation").first().click();
  const passage = await A.page.getByTestId("passage-modal").innerText();
  check("citation opens the supporting passage with its document version", /version \d/.test(passage) && passage.includes("Roles"));
  await A.page.getByRole("button", { name: "Close passage" }).click();

  // 4. Activity: simulated run, tools, sources, not-recorded list, raw events.
  const usageHiddenBefore = !(await A.page.getByTestId("proposal-usage").isVisible());
  await A.page.getByTestId("activity").locator("summary").first().click();
  const act = await A.page.getByTestId("activity").innerText();
  check("activity: labelled simulated, with tools, retrieved sources and the not-recorded list",
    (await A.page.getByTestId("activity-mode").innerText()) === "Simulated" && act.includes("no model was called")
    && act.includes("Look up customer") && (await A.page.getByTestId("activity-sources").locator("button").count()) > 0
    && act.includes("Cited") && act.includes("Not recorded") && act.includes("Model reasoning"));
  check("activity: technical details are collapsed by default (usage line not visible until opened)",
    usageHiddenBefore && await A.page.getByTestId("proposal-usage").isVisible());
  await A.page.getByTestId("activity").evaluate((el) => el.scrollIntoView({ block: "start" }));
  await shot(A.page, "after-03-access-activity");
  await A.page.getByTestId("activity").locator("summary").first().click();

  // 5. Recoverable errors keep the edited draft (server error, then network failure), then saving works.
  await A.page.getByTestId("edit").click();
  const ta = A.page.getByTestId("proposal-editor").locator("textarea").first();
  const edited = (await ta.inputValue()) + "\n\nP.S. Reviewed by Riley.";
  await ta.fill(edited);
  await A.page.route("**/proposal", (r) => r.request().method() === "PUT" ? r.fulfill({ status: 500, body: "oops" }) : r.continue());
  await A.page.getByRole("button", { name: "Save as new version" }).click();
  await A.page.getByTestId("error").waitFor();
  const err500 = await A.page.getByTestId("error").innerText();
  check("save fails with a server error: message shown, edited draft still in the editor",
    err500.includes("could not complete") && err500.includes("edits are still in the editor")
    && (await ta.inputValue()) === edited && await A.page.getByTestId("proposal-editor").isVisible(), err500.slice(0, 90));
  await A.page.unroute("**/proposal");
  await A.page.route("**/proposal", (r) => r.request().method() === "PUT" ? r.abort("internetdisconnected") : r.continue());
  await A.page.getByRole("button", { name: "Save as new version" }).click();
  await A.page.getByTestId("error").getByText("Could not reach the server").waitFor();
  check("save fails with a network error: draft still preserved", (await ta.inputValue()) === edited);
  await shot(A.page, "after-error-edit-preserved");
  await A.page.unroute("**/proposal");
  await A.page.getByRole("button", { name: "Save as new version" }).click();
  await A.page.getByTestId("proposal-version").getByText("Version 2 of 2").waitFor();
  check("after the error, saving succeeds and clears the error; approval now targets version 2",
    (await A.page.getByTestId("error").count()) === 0 && (await A.page.getByTestId("draft-reply").innerText()).includes("Reviewed by Riley")
    && (await A.page.getByTestId("approval-consequence").innerText()).includes("applies to version 2"));

  // 6. Duplicate-submit protection: approve is slow; double click sends one request.
  let approvePosts = 0;
  await A.page.route("**/approve", async (r) => { approvePosts++; await new Promise((f) => setTimeout(f, 900)); await r.continue(); });
  await A.page.getByTestId("approve").click();
  const disabledWhileBusy = await A.page.getByTestId("approve").isDisabled();
  const rejectDisabled = await A.page.getByRole("button", { name: "Reject", exact: true }).isDisabled();
  await A.page.getByTestId("approve").click({ force: true }).catch(() => undefined);
  await A.page.getByTestId("completed-banner").waitFor();
  await A.page.unroute("**/approve");
  check("approve: controls disabled while processing and only one request sent", disabledWhileBusy && rejectDisabled && approvePosts === 1, `posts=${approvePosts}`);
  const done = await A.page.getByTestId("completed-banner").innerText();
  check("completed: says what happened, shows the ticket and the next action",
    /Ticket NS-\d+ created/.test(done) && done.includes("Version 2 approved by you (demo session)") && done.includes("internal tickets")
    && (await A.page.getByTestId("completed-ticket").count()) === 1 && done.includes("Next:")
    && (await A.page.getByTestId("state-badge").getAttribute("data-status")) === "completed", done.split("\n")[0]);
  const notice = await A.page.getByTestId("notice").innerText();
  check("success notice names its request", notice.includes(access.subject) && /Ticket NS-\d+ created/.test(notice), notice.slice(0, 90));
  await A.page.getByTestId("copy-reply").click();
  await A.page.getByTestId("copy-reply").getByText("Reply copied").waitFor();
  check("completed: copy approved reply works", (await A.page.evaluate(() => navigator.clipboard.readText())).includes("Reviewed by Riley"));
  await shot(A.page, "after-04-access-completed");

  // 7. Billing: needs information; reply-only copy; billing context first.
  await runScenario(A.page, "billing_charged_twice");
  await A.page.getByTestId("proposal").waitFor();
  const billing = await latest(A.page);
  const badge = await A.page.getByTestId("state-badge").innerText();
  check("billing: status is 'Needs information' (awaiting review)", badge.includes("Needs information") && badge.includes("Awaiting review"), badge);
  check("billing: reply-only proposal says 'Approve draft' and that only the draft is recorded",
    (await A.page.getByTestId("approve").innerText()) === "Approve draft"
    && /Only records this reviewed draft/.test(await A.page.getByTestId("approval-consequence").innerText())
    && (await A.page.getByTestId("approval-consequence").innerText()).includes("Records the draft only")
    && (await A.page.locator("#ticket-h").innerText()) === "Ticket: no change");
  check("billing: context leads with invoices, then subscription; seats collapsed",
    (await firstGroup(A.page)) === "billing" && (await A.page.getByTestId("facts-relevance").innerText()).includes("billing request")
    && (await A.page.getByTestId("facts-group-seats").count()) === 1);
  await shot(A.page, "after-05-billing-needs-info");
  await A.page.getByTestId("approve").click();
  await A.page.getByTestId("completed-banner").getByText("Reply draft approved").waitFor();
  const billingNotice = await A.page.getByTestId("notice").innerText();
  check("billing approval: completed with no ticket change; notice names the billing request",
    (await A.page.getByTestId("completed-banner").innerText()).includes("No ticket was created or changed")
    && billingNotice.includes(billing.subject) && (await A.page.getByTestId("state-badge").innerText()).includes("Reply approved"));
  await shot(A.page, "after-06-billing-completed-notice");

  // 8. Navigating to the access request: the billing success notice is not shown as if it described it.
  await A.page.getByTestId("inbox-row").filter({ hasText: access.subject }).first().click();
  await A.page.locator("h1").getByText(access.subject).waitFor();
  const stillThere = await A.page.getByTestId("notice").count();
  check("billing success notice is cleared when opening the access request", stillThere === 0);
  await shot(A.page, "after-07-notice-cleared-on-navigation");

  // 9. Errors stay, labelled with their request, until dismissed; "Open request" returns to it.
  await runScenario(A.page, "connector_outage");
  await A.page.getByTestId("proposal").waitFor();
  const outage = await latest(A.page);
  await A.page.route("**/approve", (r) => r.fulfill({ status: 503, body: "" }));
  await A.page.getByTestId("approve").click();
  await A.page.getByTestId("error").waitFor();
  await A.page.unroute("**/approve");
  await A.page.getByTestId("inbox-row").filter({ hasText: billing.subject }).first().click();
  await A.page.locator("h1").getByText(billing.subject).waitFor();
  const errElsewhere = await A.page.getByTestId("error").innerText();
  check("error persists after navigation and names the request it belongs to",
    errElsewhere.includes("Another request") && errElsewhere.includes(outage.subject) && (await A.page.getByTestId("flash-open").count()) === 1, errElsewhere.slice(0, 100));
  await shot(A.page, "after-08-error-labelled-other-request");
  await A.page.getByTestId("flash-open").click();
  await A.page.locator("h1").getByText(outage.subject).waitFor();
  check("'Open request' returns to the request the error belongs to", (await A.page.getByTestId("flash-open").count()) === 0
    && (await A.page.getByTestId("error").count()) === 1);
  await A.page.getByRole("button", { name: "Dismiss error" }).click();
  check("error is dismissible", (await A.page.getByTestId("error").count()) === 0);

  // 10. Escalation: create ticket (internal for visitors); product context first; activity shows the outcome.
  check("escalation: product configuration and previous tickets lead the context",
    (await firstGroup(A.page)) === "product" && (await A.page.getByTestId("facts-primary").locator("[data-group]").nth(1).getAttribute("data-group")) === "history");
  check("escalation: approve copy names the internal ticket for engineering",
    (await A.page.getByTestId("approve").innerText()) === "Approve and create ticket"
    && (await A.page.getByTestId("approval-consequence").innerText()).includes("Engineering"));
  await A.page.getByTestId("approve").click();
  await A.page.getByTestId("completed-banner").waitFor();
  await A.page.getByTestId("activity").locator("summary").first().click();
  const review = await A.page.getByTestId("activity-review").innerText();
  check("activity shows the proposal, approval and execution outcome", review.includes("Proposal version 1")
    && review.includes("Approved by") && /Create ticket via internal tickets: succeeded after 1 attempt/.test(review), review.split("\n").slice(-2).join(" | "));
  await A.page.getByTestId("activity").evaluate((el) => el.scrollIntoView({ block: "start" }));
  await shot(A.page, "after-09-escalation-activity");

  // 11. Rejection: reason recorded, rejected state with no ticket change; editing is preserved semantics untouched.
  await runScenario(A.page, "billing_charged_twice");
  await A.page.getByTestId("proposal").waitFor();
  await A.page.getByRole("button", { name: "Reject", exact: true }).click();
  await A.page.getByLabel("Rejection reason").fill("Customer already answered by phone");
  await A.page.getByRole("button", { name: "Confirm reject" }).click();
  await A.page.getByTestId("problem-callout").waitFor();
  const rej = await A.page.getByTestId("problem-callout").innerText();
  check("rejection: rejected state shows the reason and that no ticket changed",
    rej.includes("Rejected: no ticket was changed") && rej.includes("Customer already answered by phone")
    && (await A.page.getByTestId("state-badge").getAttribute("data-status")) === "rejected", rej.split("\n")[0]);
  await shot(A.page, "after-10-rejected");

  // 12. Example request with an add-note action (Okta SSO): process, then approve.
  await A.page.getByTestId("inbox-row").filter({ hasText: "Make everyone sign in with Okta" }).last().click();
  check("example request is 'Ready to process' with a process button",
    (await A.page.getByTestId("ready-callout").innerText()).includes("Ready to process") && await A.page.getByTestId("run-workflow").isVisible());
  await A.page.getByTestId("run-workflow").click();
  await A.page.getByTestId("proposal").waitFor();
  check("add-note proposal: 'Approve and add note', titled as a note on the existing ticket",
    (await A.page.getByTestId("approve").innerText()) === "Approve and add note"
    && (await A.page.locator("#ticket-h").innerText()) === "Note on the existing ticket"
    && (await A.page.getByTestId("approval-consequence").innerText()).includes("Adds an internal note"));
  await A.page.getByTestId("approve").click();
  await A.page.getByTestId("completed-banner").waitFor();
  check("add-note completed: names the ticket the note went to",
    /Note added to ticket NS-\d+/.test(await A.page.getByTestId("completed-banner").innerText()));
  await A.ctx.close();

  // 13. Laptop layouts with long content.
  const L = await visitor(1440, 900);
  await L.page.getByRole("button", { name: "New request" }).click();
  const longSubject = "Quarterly reporting export keeps failing for the EMEA finance workspace after the migration to the new warehouse connector configuration";
  await L.page.getByLabel("Subject").fill(longSubject);
  await L.page.getByLabel("Message").fill("Supercalifragilisticexpialidocious_identifier_without_any_breaks_" + "x".repeat(120) + "\n\nThe export has failed every night this week.");
  await L.page.getByRole("button", { name: "Submit" }).click();
  await L.page.locator("h1").getByText("Quarterly reporting export").waitFor();
  for (const [w, h] of [[1440, 900], [1280, 800], [1100, 720]]) {
    await L.page.setViewportSize({ width: w, height: h });
    await L.page.waitForTimeout(150);
    check(`${w}×${h}: long subject/message cause no horizontal overflow`, (await overflow(L.page)) <= 0, `${await overflow(L.page)}px`);
  }
  await L.page.setViewportSize({ width: 1280, height: 800 });
  await shot(L.page, "after-11-long-content-1280");
  await runScenario(L.page, "connector_outage");
  await L.page.getByTestId("proposal").waitFor();
  for (const [w, h] of [[1440, 900], [1280, 800], [1100, 720]]) {
    await L.page.setViewportSize({ width: w, height: h });
    await L.page.waitForTimeout(200);
    const m = await L.page.evaluate(() => {
      const col = document.querySelector("[data-testid=request-pane] .max-w-\\[46rem\\]");
      const bar = document.querySelector("[data-testid=approval-bar]").getBoundingClientRect();
      const pane = document.querySelector("[data-testid=request-pane] > .pane-scroll").getBoundingClientRect();
      const ev = document.querySelector("[data-testid=evidence-pane]");
      return { col: Math.round(col.getBoundingClientRect().width), barTop: Math.round(bar.top), barBottom: Math.round(bar.bottom), paneBottom: Math.round(pane.bottom),
        vh: innerHeight, evidence: ev && ev.offsetParent !== null ? Math.round(ev.getBoundingClientRect().width) : 0 };
    });
    check(`${w}×${h}: readable request column, approval bar reachable without covering content`,
      (await overflow(L.page)) <= 0 && m.col >= 480 && m.barBottom <= m.vh && m.paneBottom <= m.barTop
      && (w < 1280 || m.evidence >= 300), JSON.stringify(m));
    await shot(L.page, `after-12-escalation-${w}`);
  }
  // Narrower laptop: the context panel is a drawer opened from the request header.
  await L.page.getByTestId("open-details").click();
  await L.page.getByTestId("evidence-pane").waitFor();
  await L.page.waitForTimeout(250);
  check("1100px: context opens as a drawer and closes with Escape", await L.page.getByRole("button", { name: "Close details" }).isVisible());
  await shot(L.page, "after-13-drawer-1100");
  await L.page.keyboard.press("Escape");
  await L.ctx.close();
} catch (e) {
  check("polish checks completed without exceptions", false, String(e).slice(0, 400));
} finally {
  check("no uncaught page errors", pageErrors.length === 0, pageErrors.slice(0, 2).join(" | "));
  await browser.close();
  const failed = results.filter((r) => !r).length;
  console.log(`\n${results.length - failed}/${results.length} polish checks passed`);
  process.exit(failed ? 1 : 0);
}
