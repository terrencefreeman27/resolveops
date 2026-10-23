// Milestone 5 browser checks: dashboard scoping and labelling, layout at 1440/1024/390, accessibility basics.
// Called from browser-check.mjs. Screenshots go to docs/screenshots/.
import { runScenario } from "./ui-helpers.mjs";

const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

// Controls without an accessible name (buttons, links, form fields). Basic: text, aria-label, label[for], wrapping label, title.
const unnamedControls = (page) => page.evaluate(() => {
  const bad = [];
  for (const el of document.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea")) {
    const id = el.getAttribute("id");
    const named = (el.textContent ?? "").trim() || el.getAttribute("aria-label") || el.getAttribute("aria-labelledby")
      || el.getAttribute("title") || el.closest("label") || (id && document.querySelector(`label[for="${id}"]`))
      || (el.getAttribute("placeholder") && el.tagName !== "SELECT");
    if (!named) bad.push(el.outerHTML.slice(0, 80));
  }
  return bad;
});

export async function m5({ visitor, apiCall, check, OUT }) {
  const snap = (page, name, fullPage = false) => page.screenshot({ path: `${OUT}${name}.png`, fullPage });

  // A. Visitor: run + approve a scenario, then the dashboard counts exactly that sandbox's activity.
  const A = await visitor();
  await runScenario(A.page, "connector_outage");
  await A.page.getByTestId("proposal").waitFor();
  await A.page.getByTestId("approve").click();
  await A.page.getByTestId("notice").getByText(/Ticket NS-/).waitFor();
  await A.page.getByTestId("open-dashboard").click();
  await A.page.getByTestId("dashboard").waitFor();
  const scope = await A.page.getByTestId("dashboard-scope").innerText();
  const cat = await A.page.getByTestId("dash-category").innerText();
  const ex = await A.page.getByTestId("dash-executions").innerText();
  check("dashboard (visitor) is scoped to the own sandbox and counts the approved run",
    scope.includes("Your demo sandbox only") && /Product issue\s+1/.test(cat) && /Succeeded\s+1/.test(ex), scope);
  const usage = await A.page.getByTestId("dash-usage").innerText();
  check("dashboard keeps simulated and live usage separate; cost says pricing not configured",
    (await A.page.getByTestId("runs-simulated").count()) === 1 && (await A.page.getByTestId("runs-live").count()) === 1
    && usage.includes("pricing not configured") && usage.includes("Not model latency"));
  const ev = await A.page.getByTestId("dash-eval").innerText();
  check("dashboard eval results are labelled by mode (demo simulated, live not run, backend checks)",
    ev.includes("Simulated — not evidence of AI performance") && (await A.page.getByTestId("eval-ai-live").innerText()).includes("Not run")
    && (await A.page.getByTestId("eval-backend-deterministic").count()) === 1);
  await snap(A.page, "30-dashboard-visitor-1440");
  await A.page.getByTestId("dash-eval").scrollIntoViewIfNeeded();
  await snap(A.page, "30b-dashboard-eval-1440");

  // B. A second visitor's dashboard does not see A's sandbox.
  const B = await visitor();
  await B.page.getByTestId("open-dashboard").click();
  await B.page.getByTestId("dashboard").waitFor();
  const bText = await B.page.getByTestId("dash-category").innerText();
  check("dashboard: another visitor sees none of the first visitor's activity", bText.includes("0 processed request(s)"), bText.split("\n")[1]);

  // C. Reviewer dashboard is the workspace queue.
  const R = await visitor();
  await apiCall(R.page, "POST", "/api/auth/login", { email: "reviewer@northstar.example", password: "northstar-demo" });
  await R.page.goto(`${R.page.url().split("#")[0]}#dashboard`);
  await R.page.reload();
  await R.page.getByTestId("dashboard").waitFor();
  check("dashboard (reviewer) shows the workspace queue scope",
    (await R.page.getByTestId("dashboard-scope").innerText()).includes("Workspace queue"));

  // D. Layout at 1024 and 390 for the dashboard and the three-panel workspace.
  for (const [w, h] of [[1024, 800], [390, 844]]) {
    await A.page.setViewportSize({ width: w, height: h });
    const o = await noOverflow(A.page);
    check(`dashboard ${w}px has no horizontal overflow`, o <= 0, `${o}px`);
    await snap(A.page, `31-dashboard-${w}`);
  }
  await A.page.getByTestId("open-inbox").click();
  await A.page.setViewportSize({ width: 1440, height: 900 });
  await runScenario(A.page, "access_reporting_after_upgrade");
  await A.page.getByTestId("proposal").getByText("Analyst", { exact: false }).first().waitFor();
  const o1440 = await noOverflow(A.page);
  check("workspace 1440px has no horizontal overflow", o1440 <= 0, `${o1440}px`);
  await snap(A.page, "32-workspace-1440");

  // E. Accessibility basics: every control has an accessible name; keyboard focus is visible on a button.
  const unnamed = [...await unnamedControls(A.page), ...await unnamedControls(R.page)];
  check("every button, link and form control has an accessible name", unnamed.length === 0, unnamed.slice(0, 2).join(" | "));
  await A.page.getByTestId("workspace-switcher").focus();
  await A.page.keyboard.press("Tab");
  await A.page.waitForTimeout(300); // buttons transition outline-color; read the settled style
  const ring = await A.page.evaluate(() => {
    const el = document.activeElement; if (!el) return "";
    const cs = getComputedStyle(el); return `${el.matches(":focus-visible")} ${cs.outlineStyle} ${cs.outlineWidth} ${cs.outlineColor}`;
  });
  check("keyboard focus is visible (opaque outline on the focused control)",
    /^true solid 2px /.test(ring) && !/rgba\(0, 0, 0, 0\)|transparent/.test(ring), ring.slice(0, 60));
  await A.ctx.close(); await B.ctx.close(); await R.ctx.close();
}
