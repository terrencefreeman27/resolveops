// Design QA: captures the same UI states before and after the redesign.
// Usage: node e2e/design/capture-states.mjs <before|after> [widths=1440,1280,390]
// Stress cases (long subject/name, many sources) are produced by rewriting API responses in this
// script only (page.route); nothing in the app exposes them.
import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE ?? "http://localhost:8080";
const phase = process.argv[2] ?? "after";
const widths = (process.argv[3] ?? "1440,1280,390").split(",").map(Number);
const OUT = fileURLToPath(new URL(`../../../docs/design/${phase}/`, import.meta.url));
await mkdir(OUT, { recursive: true });

const has = async (page, id) => (await page.getByTestId(id).count()) > 0;
const visible = async (page, id) => (await page.getByTestId(id).count()) > 0 && page.getByTestId(id).first().isVisible();
async function runScenario(page, key) {
  if (await has(page, "scenario-menu")) await page.getByTestId("scenario-menu").click();
  await page.getByTestId(`scenario-${key}`).click();
  await page.getByTestId("proposal").waitFor({ timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector("[data-testid^=scenario-]:disabled"));
}
async function showDetails(page) {
  if (await has(page, "tab-details") && await page.getByTestId("tab-details").isVisible()) await page.getByTestId("tab-details").click();
  else if (await has(page, "open-details") && await page.getByTestId("open-details").isVisible()) await page.getByTestId("open-details").click();
}
async function showRequest(page) {
  if (await has(page, "tab-request") && await page.getByTestId("tab-request").isVisible()) await page.getByTestId("tab-request").click();
}
async function showInbox(page) {
  if (await has(page, "tab-inbox") && await page.getByTestId("tab-inbox").isVisible()) await page.getByTestId("tab-inbox").click();
}
const shot = (page, name, w) => page.screenshot({ path: `${OUT}${name}-${w}.png` });

const LONG_SUBJECT = "Our quarterly board-reporting workspace stopped refreshing after the SSO migration and now every executive dashboard shows stale numbers from last Tuesday";
const LONG_COMPANY = "Fairweather-Montgomery International Logistics & Cold-Chain Distribution Holdings";

const browser = await chromium.launch();
try {
  for (const w of widths) {
    const h = w < 600 ? 844 : 900;
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(BASE);
    await page.getByTestId("inbox").getByText("Not processed").first().waitFor({ timeout: 20000 });
    await page.waitForTimeout(300);
    await shot(page, "01-empty-selection", w);

    await runScenario(page, "access_reporting_after_upgrade");
    await shot(page, "02-access-proposal", w);
    await showDetails(page);
    await page.waitForTimeout(200);
    await shot(page, "02b-access-context", w);
    await page.getByTestId("citation").first().click();
    await page.getByTestId("passage-modal").waitFor();
    await page.waitForTimeout(200);
    await shot(page, "03-citation-passage", w);
    await page.getByRole("button", { name: "Close passage" }).click();
    await showRequest(page);

    await runScenario(page, "billing_charged_twice");
    await shot(page, "04-billing-clarification", w);
    await page.getByTestId("edit").click();
    await page.getByTestId("proposal-editor").waitFor();
    await shot(page, "04b-editing", w);
    await page.getByTestId("proposal-editor").getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await page.waitForTimeout(150);
    await shot(page, "04c-reject-reason", w);
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "New request" }).click();
    await page.getByLabel("Subject").waitFor();
    await page.waitForTimeout(200);
    await shot(page, "04d-new-request-dialog", w);
    await page.keyboard.press("Escape");

    await runScenario(page, "connector_outage");
    await page.getByTestId("activity").locator("summary").first().click();
    await page.getByTestId("activity").locator("summary").first().evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.waitForTimeout(200);
    await shot(page, "05-escalation-timeline", w);

    // Completed: approve the escalation.
    await page.getByTestId("activity").locator("summary").first().click();
    await page.getByTestId("approve").click();
    await page.getByTestId("notice").waitFor({ timeout: 20000 });
    await page.waitForTimeout(200);
    await shot(page, "06-completed", w);

    // Processing: hold the scenario response so the in-flight state is visible.
    let release;
    const held = new Promise((r) => { release = r; });
    await page.route("**/scenarios/*/run", async (route) => { await held; await route.continue(); });
    if (await has(page, "scenario-menu")) await page.getByTestId("scenario-menu").click();
    await page.getByTestId("scenario-access_reporting_after_upgrade").click();
    await page.waitForTimeout(400);
    await shot(page, "07-processing", w);
    release();
    await page.getByTestId("proposal").waitFor();
    await page.unroute("**/scenarios/*/run");

    // Dashboard.
    await page.getByTestId("open-dashboard").click();
    await page.getByTestId("dashboard").waitFor();
    await shot(page, "08-dashboard", w);
    await page.getByTestId("open-inbox").click();
    await ctx.close();

    // Stress: long subject + long company + many sources via rewritten responses.
    const s = await browser.newContext({ viewport: { width: w, height: h } });
    const sp = await s.newPage();
    await sp.route("**/api/w/*/requests**", async (route) => {
      const res = await route.fetch(); let body = await res.json();
      const patch = (r) => { if (!r || !r.subject) return; r.subject = LONG_SUBJECT; if (r.customer) r.customer.company_name = LONG_COMPANY; r.from_name = "Maximiliana Konstantinopoulou-Abernathy"; };
      if (Array.isArray(body.requests)) body.requests.slice(0, 2).forEach(patch);
      else if (body.proposal) {
        patch(body);
        const c = body.proposal.version.content;
        const extra = [...c.citations, ...c.citations, ...c.citations].map((x, i) => ({ ...x, section: `${x.section} — appendix ${i + 1} covering edge cases for long section titles` }));
        c.citations = [...c.citations, ...extra].slice(0, 12);
      }
      await route.fulfill({ response: res, json: body });
    });
    await sp.goto(BASE);
    await sp.getByTestId("inbox").getByText("Not processed").first().waitFor({ timeout: 20000 });
    await runScenario(sp, "access_reporting_after_upgrade");
    await sp.waitForTimeout(300);
    await shot(sp, "09-stress-long-content", w);
    await showDetails(sp);
    await sp.waitForTimeout(200);
    await shot(sp, "09b-stress-sources", w);
    await showInbox(sp);
    await sp.waitForTimeout(200);
    await shot(sp, "09c-stress-inbox", w);
    await s.close();

    // Setup (reviewer).
    const r = await browser.newContext({ viewport: { width: w, height: h } });
    const rp = await r.newPage();
    await rp.goto(BASE);
    await rp.getByTestId("inbox").waitFor();
    await rp.evaluate(() => fetch("/api/auth/login", { method: "POST", headers: { "X-ResolveOps": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ email: "reviewer@northstar.example", password: "northstar-demo" }) }));
    await rp.goto(`${BASE}/#setup`);
    await rp.reload();
    await rp.getByTestId("setup").waitFor();
    await rp.getByTestId("setup-step-4").click();
    await rp.waitForTimeout(500);
    await shot(rp, "10-setup-rules", w);
    await rp.getByTestId("ai-status-open").click();
    await rp.getByTestId("ai-status-budget").waitFor();
    await rp.waitForTimeout(200);
    await shot(rp, "11-ai-status", w);
    await r.close();
    console.log("captured", w);
  }
} catch (e) {
  console.log("ERROR", String(e).slice(0, 400));
  process.exitCode = 1;
} finally {
  await browser.close();
}
