// Layout and accessibility checks for the redesigned workspace, at desktop, laptop, tablet and phone widths.
// Usage: node e2e/design/visual-checks.mjs   (BASE defaults to http://localhost:8080)
// Screenshots go to docs/design/after/.
import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { runScenario } from "../ui-helpers.mjs";

const BASE = process.env.BASE ?? "http://localhost:8080";
const OUT = fileURLToPath(new URL("../../../docs/design/after/", import.meta.url));
await mkdir(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`); };
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

// WCAG contrast of an element's text colour against the first opaque ancestor background.
const contrastOf = (p, selector) => p.evaluate((sel) => {
  const el = document.querySelector(sel); if (!el) return null;
  const parse = (c) => (c.match(/[\d.]+/g) ?? []).map(Number);
  let bg = null, n = el;
  while (n && !bg) { const c = parse(getComputedStyle(n).backgroundColor); if (c.length >= 3 && (c[3] ?? 1) >= 0.99) bg = c; n = n.parentElement; }
  bg ??= [255, 255, 255];
  const fg = parse(getComputedStyle(el).color);
  const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return +((a + 0.05) / (b + 0.05)).toFixed(2);
}, selector);

const browser = await chromium.launch();
try {
  // A. Each width: overflow, independent scrolling, approval bar placement.
  for (const [w, h] of [[1440, 900], [1280, 800], [1024, 768], [768, 1024], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    await p.goto(BASE);
    await p.getByTestId("inbox").getByText("Not processed").first().waitFor();
    await runScenario(p, "connector_outage");
    await p.getByTestId("proposal").waitFor();
    check(`${w}px: no horizontal overflow`, (await overflow(p)) <= 0, `${await overflow(p)}px`);

    const layout = await p.evaluate(() => {
      const pane = document.querySelector("[data-testid=request-pane] > .pane-scroll");
      const bar = document.querySelector("[data-testid=approval-bar]");
      const inbox = document.querySelector("[data-testid=inbox]");
      const before = { doc: document.scrollingElement.scrollTop, inbox: inbox?.scrollTop ?? 0 };
      pane.scrollTop = 400;
      const after = { doc: document.scrollingElement.scrollTop, inbox: inbox?.scrollTop ?? 0, pane: pane.scrollTop };
      const pr = pane.getBoundingClientRect(), br = bar.getBoundingClientRect();
      return { before, after, paneBottom: Math.round(pr.bottom), barTop: Math.round(br.top), barBottom: Math.round(br.bottom), vh: innerHeight,
        scrollable: pane.scrollHeight > pane.clientHeight };
    });
    check(`${w}px: request pane scrolls on its own (page and inbox stay put)`,
      layout.scrollable && layout.after.pane > 0 && layout.after.doc === 0 && layout.after.inbox === layout.before.inbox, JSON.stringify(layout.after));
    check(`${w}px: approval bar visible and not covering content`, layout.barBottom <= layout.vh && layout.paneBottom <= layout.barTop,
      `pane bottom ${layout.paneBottom}, bar ${layout.barTop}-${layout.barBottom}, viewport ${layout.vh}`);
    const approve = p.getByTestId("approve");
    check(`${w}px: approve button is in view`, await approve.isVisible() && (await approve.boundingBox()).y + 20 < h);
    if (w >= 1280) {
      // Context panel scrolls independently too.
      const ctxScroll = await p.evaluate(() => {
        const e = document.querySelector("[data-testid=evidence-pane]"); e.scrollTop = 300;
        return { ok: e.scrollTop > 0 || e.scrollHeight <= e.clientHeight, doc: document.scrollingElement.scrollTop };
      });
      check(`${w}px: context panel scrolls on its own`, ctxScroll.ok && ctxScroll.doc === 0);
    }
    if (w === 1024) {
      await p.getByTestId("open-details").click();
      await p.getByTestId("evidence-pane").waitFor();
      await p.waitForTimeout(250);
      await p.screenshot({ path: `${OUT}20-drawer-1024.png` });
      await p.keyboard.press("Escape");
      await p.waitForTimeout(100);
      check("1024px: details drawer opens from the request header and closes with Escape", !(await p.getByTestId("evidence-pane").isVisible()));
    }
    if (w <= 768) {
      await p.getByTestId("tab-details").click();
      const vis = await p.getByTestId("evidence-pane").isVisible();
      await p.getByTestId("tab-inbox").click();
      const inboxVis = await p.getByTestId("inbox").isVisible();
      check(`${w}px: tabs switch between inbox, request and details`, vis && inboxVis);
      check(`${w}px: no horizontal overflow on the inbox tab`, (await overflow(p)) <= 0);
    }
    await ctx.close();
  }

  // B. Keyboard: arrow keys through inbox rows, Enter opens, focus ring visible; menus close with Escape.
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await p.goto(BASE);
  await p.getByTestId("inbox").getByText("Not processed").first().waitFor();
  await p.getByTestId("inbox-row").first().focus();
  await p.keyboard.press("ArrowDown");
  const second = await p.evaluate(() => document.activeElement === document.querySelectorAll("[data-testid=inbox-row]")[1]);
  await p.keyboard.press("Enter");
  await p.getByTestId("request-pane").waitFor();
  const current = await p.evaluate(() => document.querySelectorAll("[data-testid=inbox-row]")[1].getAttribute("aria-current"));
  const ring = await p.evaluate(() => { const cs = getComputedStyle(document.activeElement); return `${cs.outlineStyle} ${cs.outlineWidth}`; });
  check("keyboard: ArrowDown moves between inbox rows, Enter opens, focus ring visible", second && current === "true" && ring === "solid 2px", `${second} ${current} ${ring}`);
  await p.screenshot({ path: `${OUT}21-keyboard-focus-1440.png` });
  await p.getByTestId("scenario-menu").focus();
  await p.keyboard.press("Enter");
  await p.getByTestId("scenario-panel").waitFor();
  await p.waitForTimeout(250);
  const inMenu = await p.evaluate(() => document.activeElement?.closest("[data-testid=scenario-panel]") !== null);
  await p.screenshot({ path: `${OUT}22-scenario-menu-1440.png` });
  await p.keyboard.press("Escape");
  const back = await p.evaluate(() => document.activeElement?.getAttribute("data-testid"));
  check("keyboard: scenario menu takes focus and Escape returns it to the trigger", inMenu && back === "scenario-menu", `${inMenu} ${back}`);
  await p.getByTestId("account-menu").click();
  await p.getByTestId("account-panel").waitFor();
  await p.waitForTimeout(250);
  await p.screenshot({ path: `${OUT}23-account-menu-1440.png` });
  await p.keyboard.press("Escape");
  await p.getByRole("button", { name: "About this mode" }).click();
  await p.getByTestId("mode-help").waitFor();
  await p.waitForTimeout(250);
  check("demo label explains itself in contextual help", (await p.getByTestId("mode-help").innerText()).includes("synthetic data"));
  await p.screenshot({ path: `${OUT}24-mode-help-1440.png` });
  await p.keyboard.press("Escape");

  // C. Contrast of real rendered text (body ≥ 4.5:1).
  await runScenario(p, "access_reporting_after_upgrade");
  await p.getByTestId("proposal").waitFor();
  await p.getByTestId("activity").locator("summary").first().click(); // usage line lives in Activity
  const pairs = {
    "draft reply body": await contrastOf(p, "[data-testid=draft-reply]"),
    "proposal usage (subtle)": await contrastOf(p, "[data-testid=proposal-usage]"),
    "inbox row preview (selected row)": await contrastOf(p, "[data-testid=inbox-row][aria-current] .line-clamp-2"),
    "inbox row preview (canvas)": await contrastOf(p, "[data-testid=inbox-row]:not([aria-current]) .line-clamp-2"),
    "fact label (canvas)": await contrastOf(p, "[data-testid=evidence-pane] dt"),
    "mode label": await contrastOf(p, "[data-testid=mode-banner]"),
    "approve button": await contrastOf(p, "[data-testid=approve]"),
  };
  check("text contrast ≥ 4.5:1 on sampled pairs", Object.values(pairs).every((v) => v >= 4.5), JSON.stringify(pairs));

  // D. Empty inbox (fresh visitor, seeded examples collapsed) and a no-match search.
  const e = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  await e.goto(BASE);
  await e.getByTestId("inbox").getByText("Not processed").first().waitFor();
  await e.getByTestId("seeded-section").locator("summary").click();
  await e.waitForTimeout(150);
  check("empty session shows guidance", (await e.getByTestId("inbox").innerText()).includes("Nothing here yet"));
  await e.screenshot({ path: `${OUT}25-empty-inbox-1280.png` });
  await e.getByPlaceholder("Search subject, customer or sender").fill("zzz-no-such-request");
  check("search with no matches says so", (await e.getByTestId("inbox").innerText()).includes("No requests match"));
  await e.screenshot({ path: `${OUT}26-no-results-1280.png` });
} catch (err) {
  check("visual checks completed without exceptions", false, String(err).slice(0, 300));
} finally {
  await browser.close();
  const failed = results.filter((r) => !r).length;
  console.log(`\n${results.length - failed}/${results.length} visual checks passed`);
  process.exit(failed ? 1 : 0);
}
