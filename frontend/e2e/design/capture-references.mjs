// Research only: captures the four public reference pages named in the redesign brief into
// docs/design/references/ and lists the product images they embed. Not part of any check suite.
import { chromium } from "playwright-core";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../../../docs/design/references/", import.meta.url));
const PAGES = {
  "intercom-inbox": "https://www.intercom.com/helpdesk/inbox",
  "intercom-inbox-explained": "https://www.intercom.com/help/en/articles/6258745-the-inbox-explained",
  "linear-triage": "https://linear.app/docs/triage",
  "langfuse-observability": "https://langfuse.com/docs/observability/overview",
};
const browser = await chromium.launch();
const report = {};
for (const [name, url] of Object.entries(PAGES)) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
    userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" });
  const page = await ctx.newPage();
  try {
    const res = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(4000);
    // Trigger lazy images.
    for (let y = 0; y < 12; y++) { await page.mouse.wheel(0, 1200); await page.waitForTimeout(250); }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true, timeout: 60000 });
    const imgs = await page.evaluate(() => [...document.querySelectorAll("img")]
      .map((i) => ({ src: i.currentSrc || i.src, alt: i.alt, w: i.naturalWidth, h: i.naturalHeight }))
      .filter((i) => i.w >= 600));
    report[name] = { url, status: res?.status(), title: await page.title(), imgs };
    console.log(name, res?.status(), imgs.length, "large images");
  } catch (e) {
    report[name] = { url, error: String(e).slice(0, 200) };
    console.log(name, "ERROR", String(e).slice(0, 200));
  }
  await ctx.close();
}
await writeFile(`${OUT}images.json`, JSON.stringify(report, null, 2));
await browser.close();
