// Milestone 4 browser checks: the GitHub Issues adapter is visibly "not configured" (with the server's
// reason) for reviewers, the status panel shows only yes/no + destination, and visitors never get a
// GitHub execution. Runs against the default stack (GITHUB_ADAPTER_ENABLED unset). Called from browser-check.mjs.

export async function m4({ visitor, apiCall, check, OUT, expectedHttp }) {
  const snap = (page, name) => page.screenshot({ path: `${OUT}${name}.png` });

  // A. Reviewer: adapter step shows GitHub as not configured, with the reason, and the server refuses it.
  const R = await visitor();
  await apiCall(R.page, "POST", "/api/auth/login", { email: "reviewer@northstar.example", password: "northstar-demo" });
  await R.page.goto(`${R.page.url().split("#")[0]}#setup`);
  await R.page.reload();
  await R.page.getByTestId("setup").waitFor();
  await R.page.getByTestId("setup-step-5").click();
  await R.page.getByTestId("adapter-list").waitFor();
  const list = await R.page.getByTestId("adapter-list").innerText();
  const ghDisabled = await R.page.getByTestId("adapter-github").isDisabled();
  check("reviewer adapter step: GitHub not configured, with the server's reason",
    ghDisabled && list.includes("Not configured") && list.includes("GITHUB_ADAPTER_ENABLED"), list.split("\n").slice(-1)[0]?.slice(0, 90));
  expectedHttp.add("HTTP 409 PUT /api/w/northstar/admin/adapter");
  const forced = await apiCall(R.page, "PUT", "/api/w/northstar/admin/adapter", { adapter: "github" });
  check("server refuses selecting GitHub when it is not configured", forced.status === 409, `${forced.status}`);
  await snap(R.page, "22-adapter-github-not-configured");

  // B. Status panel: configured yes/no + destination/reason only; no token material.
  await R.page.goto(R.page.url().split("#")[0]);
  await R.page.getByTestId("ai-status-open").click();
  await R.page.getByTestId("ai-status-github").waitFor();
  const gh = await R.page.getByTestId("ai-status-github").innerText();
  const panel = await R.page.getByTestId("ai-status").innerText();
  const status = (await apiCall(R.page, "GET", "/api/w/northstar/ai/status")).data.github;
  check("status panel shows GitHub configured: No, without any token",
    gh.includes("No") && !/github_pat_|ghp_|token[:=]/i.test(panel) && Object.keys(status).sort().join() === "configured,enabled,reason,repo,token_configured",
    gh.replace(/\s+/g, " "));
  await snap(R.page, "23-status-github");

  // C. Visitor: an escalation executes through the internal adapter; GitHub endpoints are refused.
  const V = await visitor();
  await V.page.getByTestId("scenario-connector_outage").click();
  await V.page.getByTestId("proposal").getByText("Escalate", { exact: true }).waitFor();
  await V.page.getByTestId("approve").click();
  await V.page.getByTestId("notice").getByText("Ticket").waitFor();
  const card = await V.page.getByTestId("ticket").first().innerText();
  const links = await V.page.getByTestId("ticket-external-link").count();
  const history = await V.page.getByTestId("history").innerText();
  check("visitor escalation uses the internal adapter, no GitHub link",
    card.includes("internal adapter") && links === 0 && history.includes("via internal adapter") && !/github/i.test(history), card.split("\n")[0]);
  for (const p of ["HTTP 403 PUT /api/w/northstar/admin/adapter", "HTTP 403 GET /api/w/northstar/ai/status"]) expectedHttp.add(p);
  const probes = [await apiCall(V.page, "PUT", "/api/w/northstar/admin/adapter", { adapter: "github" }),
                  await apiCall(V.page, "GET", "/api/w/northstar/ai/status")];
  check("visitor cannot select adapters or read GitHub status (server 403)", probes.every((r) => r.status === 403),
    probes.map((r) => r.status).join(","));
  await snap(V.page, "24-visitor-escalation-internal");
}
