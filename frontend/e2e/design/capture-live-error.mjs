// Design QA for live mode without ANTHROPIC_API_KEY (run only while the API is temporarily set to AI_MODE=live):
// visitor label, reviewer label, and the reviewer's request ending in the error state. Screenshots: docs/design/<phase>/.
import { chromium } from "playwright-core";
import { fileURLToPath } from "node:url";
import { runScenario } from "../ui-helpers.mjs";
const BASE = process.env.BASE ?? "http://localhost:8080";
const OUT = fileURLToPath(new URL(`../../../docs/design/${process.argv[2] ?? "after"}/`, import.meta.url));
const browser = await chromium.launch();
try {
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const p = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
    await p.goto(BASE);
    await p.getByTestId("inbox").waitFor();
    await p.screenshot({ path: `${OUT}30-live-visitor-${w}.png` });
    await p.evaluate(() => fetch("/api/auth/login", { method: "POST", headers: { "X-ResolveOps": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ email: "reviewer@northstar.example", password: "northstar-demo" }) }));
    await p.reload();
    await p.getByTestId("mode-banner").getByText("Live").waitFor();
    console.log(w, "banner:", await p.getByTestId("mode-banner").innerText());
    await runScenario(p, "access_reporting_after_upgrade");
    await p.waitForFunction(() => !document.querySelector("[data-testid=scenario-menu]:disabled"), null, { timeout: 30000 });
    await p.waitForTimeout(400);
    console.log(w, "pane:", (await p.getByTestId("request-pane").innerText()).slice(0, 300).replace(/\n/g, " | "));
    await p.screenshot({ path: `${OUT}31-live-error-${w}.png` });
  }
} catch (e) { console.log("ERROR", String(e).slice(0, 300)); process.exitCode = 1; }
finally { await browser.close(); }
