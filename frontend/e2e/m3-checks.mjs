// Milestone 3 browser checks: reviewer onboarding, document lifecycle + stale proposals, second company,
// and visitors locked out of onboarding. Called from browser-check.mjs with its helpers.
import { runScenario } from "./ui-helpers.mjs";

const latestId = (page, ws) => page.evaluate(async (ws) => {
  const d = await (await fetch(`/api/w/${ws}/requests`)).json();
  return d.requests.filter((x) => !x.is_template).sort((a, b) => b.received_at.localeCompare(a.received_at))[0]?.id;
}, ws);

const file = (name, text) => ({ name, mimeType: name.endsWith(".md") ? "text/markdown" : "application/octet-stream", buffer: Buffer.from(text) });

export async function m3({ visitor, apiCall, check, OUT, expectedHttp }) {
  const snap = (page, name) => page.screenshot({ path: `${OUT}${name}.png` });

  // A. Visitors cannot open onboarding (UI and server).
  const V = await visitor();
  await V.page.goto(`${V.page.url().split("#")[0]}#setup`);
  await V.page.getByTestId("setup-denied").waitFor();
  for (const p of ["HTTP 403 GET /api/w/northstar/admin/documents", "HTTP 403 POST /api/workspaces", "HTTP 403 POST /api/w/northstar/admin/documents"]) expectedHttp.add(p);
  const probes = [
    await apiCall(V.page, "GET", "/api/w/northstar/admin/documents"),
    await apiCall(V.page, "POST", "/api/workspaces", { name: "Visitor Co" }),
    await apiCall(V.page, "POST", "/api/w/northstar/admin/documents", { filename: "x.md", content: "# x\n\n## y\nz" }),
  ];
  check("visitor cannot open onboarding (UI + server 403)", probes.every((r) => r.status === 403), probes.map((r) => r.status).join(","));
  await snap(V.page, "14-onboarding-visitor-denied");

  // B. Reviewer onboarding: create workspace, import .md, see ready, view sections, rule, adapter, test request.
  const R = await visitor();
  await apiCall(R.page, "POST", "/api/auth/login", { email: "reviewer@northstar.example", password: "northstar-demo" });
  await R.page.goto(`${R.page.url().split("#")[0]}#setup`);
  await R.page.reload();
  await R.page.getByTestId("setup").waitFor();
  await R.page.getByTestId("setup-step-1").click();
  const company = `Acme Widgets ${Date.now().toString(36)}`;
  if (await R.page.getByRole("button", { name: "Create another workspace" }).count()) await R.page.getByRole("button", { name: "Create another workspace" }).click();
  await R.page.getByTestId("company-name").fill(company);
  await R.page.getByTestId("company-groups").fill("Support, Billing");
  await R.page.getByTestId("company-save").click();
  await R.page.getByText("Step 2 of 6").waitFor();
  const switched = await R.page.getByTestId("workspace-switcher").evaluate((el) => el.selectedOptions[0]?.textContent ?? "");
  check("reviewer creates a workspace and becomes its reviewer", switched.startsWith(company), switched);
  const slug = await R.page.getByTestId("workspace-switcher").inputValue();

  expectedHttp.add(`HTTP 415 POST /api/w/${slug}/admin/documents`);
  await R.page.getByTestId("doc-file").setInputFiles(file("policy.pdf", "%PDF-1.7 fake"));
  const rejected = await R.page.getByTestId("setup-error").innerText();
  check("unsupported file type is rejected with a clear message", rejected.includes("not supported") && rejected.includes(".md"), rejected.slice(0, 90));
  await R.page.getByTestId("doc-file").setInputFiles(file("refund-policy.md",
    "# Refund Policy\n\n## Refund window\nRefunds are available within 30 days of purchase.\n\n## Who decides\nThe Billing team approves every refund.\n"));
  await R.page.getByTestId("import-status").getByText("ready").waitFor();
  check("imported .md reaches import status ready", true);
  await snap(R.page, "15-onboarding-import");
  await R.page.getByTestId("setup-next").click();
  await R.page.getByTestId("doc-view").first().click();
  await R.page.getByTestId("doc-sections").waitFor();
  const sections = await R.page.getByTestId("doc-sections").locator("li").count();
  check("document contents shown as sections", sections === 2, `${sections}`);
  await snap(R.page, "16-onboarding-sections");
  await R.page.getByTestId("setup-next").click();
  await R.page.getByTestId("rule-name").fill("Refunds to Billing");
  await R.page.getByTestId("rule-keywords").fill("refund");
  await R.page.getByTestId("rule-group").selectOption("Billing");
  await R.page.getByTestId("rule-priority").selectOption("high");
  await R.page.getByTestId("rule-save").click();
  await R.page.getByTestId("rule").getByText("Refunds to Billing").waitFor();
  check("escalation rule saved", true);
  await snap(R.page, "17-onboarding-rules");
  await R.page.getByTestId("setup-next").click();
  await R.page.getByTestId("adapter-list").waitFor();
  const internal = await R.page.getByTestId("adapter-internal").isChecked();
  const github = await R.page.getByTestId("adapter-github").isDisabled();
  await R.page.getByTestId("adapter-internal").check();
  check("internal adapter selected; GitHub shown as not configured", internal && github
    && (await R.page.getByTestId("adapter-list").innerText()).includes("Not configured"));
  await snap(R.page, "18-onboarding-adapter");
  await R.page.getByTestId("setup-next").click();
  await R.page.getByTestId("test-text").fill("Can I get a refund for an order from last week?");
  await R.page.getByTestId("test-run").click();
  await R.page.getByTestId("test-result").waitFor();
  const outcome = await R.page.getByTestId("test-result").innerText();
  check("test request retrieves the imported doc and applies the rule", outcome.includes("Evidence: sufficient")
    && outcome.includes("Refund Policy") && outcome.includes("Refunds to Billing"), outcome.split("\n")[0]);
  await snap(R.page, "19-onboarding-test-request");
  await R.page.setViewportSize({ width: 390, height: 844 });
  const ov = await R.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("onboarding at 390px has no horizontal overflow", ov <= 0, `${ov}px`);
  await R.page.setViewportSize({ width: 1440, height: 900 });

  // C. Replace a policy doc → pending proposal stale → approve refused → reprocess gives a new version.
  await R.page.getByTestId("workspace-switcher").selectOption("northstar");
  await R.page.getByTestId("open-inbox").click();
  await runScenario(R.page, "access_reporting_after_upgrade");
  await R.page.getByTestId("proposal").waitFor();
  const reqId = await latestId(R.page, "northstar");
  const before = (await apiCall(R.page, "GET", `/api/w/northstar/requests/${reqId}`)).data;
  const roles = (await apiCall(R.page, "GET", "/api/w/northstar/admin/documents")).data.documents.find((d) => d.slug === "roles-and-permissions");
  const original = (await apiCall(R.page, "GET", `/api/w/northstar/admin/documents/${roles.id}`)).data.content;
  await R.page.getByTestId("open-setup").click();
  await R.page.getByTestId("setup-step-3").click();
  await R.page.locator('[data-testid=doc-row][data-slug="roles-and-permissions"]').getByTestId("doc-view").click();
  await R.page.getByTestId("doc-detail").waitFor();
  await R.page.getByTestId("doc-replace-file").setInputFiles(file("roles-and-permissions.md",
    original + "\nRole changes are recorded in the account's audit log.\n"));
  const nextV = roles.versions[0].version + 1;
  await R.page.getByTestId("doc-detail").getByText(`v${nextV} active`).waitFor();
  for (let i = 0; i < 40 && (await apiCall(R.page, "GET", `/api/w/northstar/requests/${reqId}`)).data.state !== "stale"; i++) {
    await R.page.waitForTimeout(250);
  }
  await R.page.getByTestId("open-inbox").click();
  await R.page.getByTestId("inbox").getByText("Stale evidence").first().click();
  await R.page.getByTestId("stale-banner").waitFor();
  const banner = await R.page.getByTestId("stale-banner").innerText();
  check("pending proposal shows stale after the policy doc is replaced", banner.includes("superseded by v"), banner.split("\n")[1]);
  const refused = await apiCall(R.page, "POST", `/api/w/northstar/requests/${reqId}/approve`,
    { proposal_version_id: before.proposal.version.id, action_hash: before.proposal.version.action_hash });
  check("approving the stale proposal is refused by the server", refused.status === 409 && refused.data.detail.includes("stale"), refused.data.detail?.slice(0, 80));
  await R.page.getByTestId("citation").first().waitFor();
  await snap(R.page, "20-stale-proposal");
  // Restore the seeded wording as a new version (so the demo reads as before), then reprocess against it.
  await apiCall(R.page, "POST", `/api/w/northstar/admin/documents/${roles.id}/versions`, { filename: "roles-and-permissions.md", content: original });
  for (let i = 0; i < 40; i++) {
    const d = (await apiCall(R.page, "GET", `/api/w/northstar/admin/documents/${roles.id}`)).data;
    if (d.versions[0].import_status === "ready") break;
    await R.page.waitForTimeout(250);
  }
  await R.page.getByTestId("reprocess").click();
  await R.page.getByTestId("proposal-version").getByText("Version 2 of 2").waitFor();
  const after = (await apiCall(R.page, "GET", `/api/w/northstar/requests/${reqId}`)).data;
  const oldCite = before.proposal.version.content.citations.find((c) => c.doc_slug === "roles-and-permissions");
  const oldPassage = (await apiCall(R.page, "GET", `/api/w/northstar/chunks/${oldCite.chunk_id}`)).data;
  check("reprocess produces v2 on current docs; old citation still opens its superseded version",
    after.state === "awaiting_review" && after.proposal.current_version === 2 && oldPassage.version_status === "superseded"
    && oldPassage.version === oldCite.version, `v${oldPassage.version} ${oldPassage.version_status}, current v${oldPassage.current_version}`);
  await snap(R.page, "21-reprocessed");

  // D. Switch company: the same request gets a different, evidence-based answer.
  const C = await visitor();
  await runScenario(C.page, "access_reporting_after_upgrade");
  await C.page.getByTestId("proposal").waitFor();
  const ns = (await apiCall(C.page, "GET", `/api/w/northstar/requests/${await latestId(C.page, "northstar")}`)).data;
  await C.page.getByTestId("workspace-switcher").selectOption("lumen");
  await C.page.getByTestId("inbox").getByText("Seeded, not run").first().waitFor();
  await runScenario(C.page, "access_reporting_after_upgrade");
  await C.page.getByTestId("draft-reply").getByText("Scale").waitFor();
  const ll = (await apiCall(C.page, "GET", `/api/w/lumen/requests/${await latestId(C.page, "lumen")}`)).data;
  const nsDocs = new Set(ns.proposal.version.content.citations.map((c) => c.document_id));
  const llDocs = ll.proposal.version.content.citations.map((c) => c.document_id);
  check("switching company: same wording, different cited docs and answer",
    ns.body === ll.body && llDocs.length > 0 && llDocs.every((d) => !nsDocs.has(d))
    && ns.proposal.version.content.draft_reply.includes("Analyst") && ll.proposal.version.content.draft_reply.includes("Scale"));
  await snap(C.page, "22-lumen-same-request");
  await runScenario(C.page, "downgrade_timing_conflict");
  await C.page.getByTestId("evidence-check").waitFor();
  const ev = await C.page.getByTestId("evidence-check").getAttribute("data-status");
  check("conflicting documents are flagged and the proposal escalates", ev === "conflicting"
    && (await C.page.getByTestId("proposal").innerText()).includes("Escalate"));
  await snap(C.page, "23-conflicting-evidence");
}
