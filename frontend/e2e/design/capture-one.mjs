// Research only: capture a single reference page with hard timeouts. Usage: node capture-one.mjs <name> <url>
import { chromium } from "playwright-core";
import { fileURLToPath } from "node:url";
const OUT = fileURLToPath(new URL("../../../docs/design/references/", import.meta.url));
const [name, url] = process.argv.slice(2);
const browser = await chromium.launch();
try {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  const res = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true, timeout: 20000 });
  console.log(name, res?.status(), await page.title());
} catch (e) { console.log("ERROR", String(e).slice(0, 200)); }
finally { await browser.close(); }
