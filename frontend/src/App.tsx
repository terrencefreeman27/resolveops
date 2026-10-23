import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Play, Unplug, X } from "lucide-react";
import { completedTitle } from "./labels";
import { executionResult } from "./components/Activity";
import { api, ApiError, type Meta, type Passage, type RequestDetail, type RequestSummary, type Scenario } from "./api";
import { LoginDialog, NewRequestDialog } from "./components/Dialogs";
import { AiStatusDialog } from "./components/AiStatusDialog";
import { FlashBar, Rail, TopBar, type Flash, type View } from "./components/AppShell";
import { EvidencePane } from "./components/EvidencePane";
import { Inbox, type Filters } from "./components/Inbox";
import { PassageModal } from "./components/PassageModal";
import { RequestPane } from "./components/RequestPane";
import { SetupView } from "./components/setup/SetupView";
import { DashboardView } from "./components/DashboardView";
import { Button, IconButton } from "./components/ui";

type Tab = "inbox" | "request" | "details";
const viewFromHash = (): View => (location.hash === "#setup" ? "setup" : location.hash === "#dashboard" ? "dashboard" : "inbox");

function Processing({ label }: { label: string }) {
  // No step list or progress bar: the server runs the workflow in one request and reports what actually
  // executed afterwards (see Activity). Showing steps here would claim progress we can't observe.
  return (
    <section className="flex h-full items-start justify-center overflow-y-auto bg-surface px-6 pt-16" role="status" aria-live="polite" data-testid="processing">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2.5">
          <LoaderCircle aria-hidden className="size-5 animate-spin text-accent" strokeWidth={2} />
          <h1 className="text-lg font-semibold text-fg [overflow-wrap:anywhere]">Processing “{label}”</h1>
        </div>
        <p className="mt-1.5 text-ui leading-relaxed text-fg-muted">The workflow classifies the request, looks up the authorized account, searches this workspace's documentation and drafts a proposal. It stops there: nothing is sent or changed until you approve.</p>
        <p className="mt-3 text-xs text-fg-subtle">The steps that ran, with their results and timing, appear under Activity when it finishes.</p>
      </div>
    </section>
  );
}

function EmptyRequest({ scenarios, busy, onRun }: { scenarios: Scenario[]; busy: boolean; onRun: (s: Scenario) => void }) {
  return (
    <section className="flex h-full items-start justify-center overflow-y-auto bg-surface px-6 pt-16">
      <div className="w-full max-w-md">
        <h1 className="text-lg font-semibold text-fg">Pick a request, or try a scenario</h1>
        <p className="mt-1.5 text-ui leading-relaxed text-fg-muted">Each scenario runs the real workflow: tools look up the authorized account, retrieval finds documentation, and nothing changes until you approve.</p>
        {scenarios.length > 0 && (
          <ul className="mt-5 divide-y divide-line rounded-lg ring-1 ring-line">
            {scenarios.map((s) => (
              <li key={s.key}>
                <button onClick={() => onRun(s)} disabled={busy} data-testid={`start-${s.key}`}
                  className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors first:rounded-t-lg last:rounded-b-lg hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-60">
                  <span className="min-w-0 flex-1">
                    <span className="block text-ui font-medium text-fg">{s.label}</span>
                    <span className="block text-xs text-fg-subtle">{s.description}</span>
                  </span>
                  <Play aria-hidden className="size-4 shrink-0 text-fg-subtle transition-colors group-hover:text-accent" strokeWidth={1.75} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [filters, setFilters] = useState<Filters>({ state: "", category: "" });
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Notifications. Request-specific ones carry the request id and subject: success notices are cleared
  // when you navigate to another request; errors stay (labelled with their request) until dismissed or resolved.
  const [error, setErrorFlash] = useState<Flash | null>(null);
  const [notice, setNoticeFlash] = useState<Flash | null>(null);
  const setError = (text: string | null, req?: { id: string; subject: string } | null) =>
    setErrorFlash(text ? { text, requestId: req?.id, subject: req?.subject } : null);
  const setNotice = (text: string | null, req?: { id: string; subject: string } | null) =>
    setNoticeFlash(text ? { text, requestId: req?.id, subject: req?.subject } : null);
  const inFlight = useRef(false);
  const selectedRef = useRef<string | null>(null);
  const [dialog, setDialog] = useState<"login" | "new" | "ai" | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [wsSlug, setWsSlug] = useState<string>(() => localStorage.getItem("ro_ws") ?? "");
  const [view, setView] = useState<View>(viewFromHash);
  const [tab, setTab] = useState<Tab>("inbox");
  const [drawer, setDrawer] = useState(false);

  selectedRef.current = selectedId;
  const ws = meta?.workspaces.find((w) => w.slug === wsSlug) ?? meta?.workspaces[0];
  const slug = ws?.slug ?? "";

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector("dialog[open]")) setDrawer(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);
  // Setup changes and workspace switches can change request states, so the cached list is dropped
  // rather than shown with outdated states while the reload is in flight.
  const clearList = () => { setRequests([]); setLoading(true); };
  const go = (v: View) => { if (v !== view) clearList(); location.hash = v === "inbox" ? "" : v; setView(v); };
  const switchWorkspace = (next: string) => {
    clearList();
    localStorage.setItem("ro_ws", next); setWsSlug(next); setSelectedId(null); setDetail(null); setError(null); setNotice(null); setTab("inbox");
  };
  const select = (id: string) => {
    if (notice?.requestId && notice.requestId !== id) setNoticeFlash(null);
    setSelectedId(id); setTab("request");
  };

  const loadMeta = useCallback(async () => {
    try {
      await api.startDemo();
      setMeta(await api.meta());
    } catch (e) {
      setFatal(e instanceof Error ? e.message : "Could not reach the API.");
    }
  }, []);

  const loadRequests = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    try { setRequests((await api.requests(slug, filters)).requests); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [slug, filters]);

  useEffect(() => { loadMeta(); }, [loadMeta]);
  // Reload when returning from setup too: document or rule changes there can mark requests stale.
  useEffect(() => { if (view === "inbox") loadRequests(); }, [loadRequests, view]);
  useEffect(() => {
    if (!slug || !selectedId) { setDetail(null); return; }
    api.request(slug, selectedId).then(setDetail).catch((e: ApiError) => {
      setDetail(null);
      if (e.status === 404) setSelectedId(null); else setError(e.message);
    });
  }, [slug, selectedId, view]);

  async function act(kind: string, fn: () => Promise<RequestDetail>, okMessage?: (d: RequestDetail) => string | null,
    target?: { id: string; subject: string }) {
    if (inFlight.current) return false; // one review action at a time: no duplicate submissions
    inFlight.current = true;
    setBusy(true); setBusyAction(kind); setNotice(null);
    if (!error?.requestId || error.requestId === target?.id) setError(null);
    try {
      const d = await fn();
      // If the reviewer moved to another request while this was running, stay there; the notice then
      // names the request it refers to instead of appearing to describe the open one.
      if (!target || selectedRef.current === target.id) {
        setDetail(d);
        setSelectedId(d.id);
        setTab("request");
      }
      const msg = okMessage?.(d);
      if (msg) setNotice(msg, d);
      await loadRequests();
      return true;
    } catch (e) {
      const msg = (e as Error).message;
      setError(kind === "edit" ? `${msg} Your edits are still in the editor.` : msg, target ?? null);
      if (target) api.request(slug, target.id).then((d) => setDetail((cur) => (cur?.id === d.id ? d : cur))).catch(() => undefined);
      return false;
    } finally { inFlight.current = false; setBusy(false); setBusyAction(null); setRunning(null); }
  }
  const runScenario = (s: Scenario) => {
    if (view !== "inbox") go("inbox");
    setRunning(s.label); setTab("request");
    return act("scenario", () => api.runScenario(slug, s.key), (d) => d.state === "awaiting_review" ? "Proposal ready for review." : null);
  };
  const cite = async (id: string) => { try { setPassage(await api.passage(slug, id)); } catch (e) { setError((e as Error).message); } };

  const outcome = (d: RequestDetail) =>
    d.state === "completed" ? (d.executions.at(-1)?.action_type === "none" ? "Reply draft approved; no ticket change."
      : `Approved. ${completedTitle(d.executions.at(-1)?.action_type, d.tickets, executionResult(d))}.`)
    : d.state === "failed" ? "Execution failed. Details are under Activity; retrying is safe." : null;

  if (fatal) {
    return (
      <main className="grid min-h-[100dvh] place-items-center bg-canvas p-6 text-center">
        <div className="max-w-sm">
          <Unplug aria-hidden className="mx-auto size-6 text-fg-subtle" strokeWidth={1.75} />
          <h1 className="mt-3 text-lg font-semibold text-fg">ResolveOps is not reachable</h1>
          <p className="mt-1 text-ui text-fg-muted">{fatal}</p>
          <Button className="mt-4" variant="primary" onClick={() => { setFatal(null); loadMeta(); }}>Try again</Button>
        </div>
      </main>
    );
  }

  const target = detail ? { id: detail.id, subject: detail.subject } : undefined;
  const signedIn = !!meta?.reviewer;
  const isReviewer = signedIn && !!ws?.is_member; // reviewer access is per workspace
  const scenarios = ws?.demo_scenarios ?? [];
  const tabs: { t: Tab; label: string }[] = [{ t: "inbox", label: "Inbox" }, { t: "request", label: "Request" }, { t: "details", label: "Details" }];

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden md:flex-row">
      <Rail view={view} go={go} signedIn={signedIn} isReviewer={isReviewer} meta={meta} ws={ws} busy={busy}
        onAiStatus={() => setDialog("ai")} onSignIn={() => setDialog("login")}
        onSignOut={async () => { await api.logout(); setSelectedId(null); go("inbox"); await loadMeta(); }}
        onReset={async () => {
          setBusy(true);
          try { await api.resetDemo(); setSelectedId(null); setNotice("Your demo session was reset. Other visitors are unaffected."); await loadRequests(); }
          catch (e) { setError((e as Error).message); } finally { setBusy(false); }
        }} />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <TopBar meta={meta} ws={ws} slug={slug} onWorkspace={switchWorkspace} query={query} setQuery={setQuery} showInboxTools={view === "inbox"}
          scenarios={scenarios} busy={busy} onRunScenario={runScenario} onNewRequest={() => setDialog("new")} />
        <FlashBar error={error} notice={notice} currentId={selectedId}
          onOpen={(id) => { if (view !== "inbox") go("inbox"); select(id); }}
          onDismiss={() => { setError(null); setNotice(null); }} />

        {view === "dashboard" ? (
          <div className="pane-scroll min-h-0 flex-1 overflow-y-auto">
            <DashboardView key={slug + (isReviewer ? ":r" : ":v")} ws={slug} onOpenInbox={() => go("inbox")} />
          </div>
        ) : view === "setup" ? (
          <SetupView meta={meta} ws={ws ?? null} signedIn={signedIn} onSignIn={() => setDialog("login")}
            onWorkspaceCreated={async (newSlug) => { await loadMeta(); switchWorkspace(newSlug); }}
            onMetaChanged={loadMeta} onOpenInbox={() => go("inbox")} />
        ) : (
          <>
            <div role="tablist" aria-label="Workspace panels" className="flex shrink-0 border-b border-line bg-surface px-2 lg:hidden">
              {tabs.map(({ t, label }) => (
                <button key={t} role="tab" aria-selected={tab === t} data-testid={`tab-${t}`} onClick={() => setTab(t)}
                  disabled={t !== "inbox" && !detail && !running}
                  className={`relative h-10 flex-1 text-ui font-medium transition-colors disabled:text-fg-subtle/50 ${tab === t ? "text-fg" : "text-fg-subtle hover:text-fg"}`}>
                  {label}
                  {tab === t && <span aria-hidden className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-accent" />}
                </button>
              ))}
            </div>
            <main className="relative grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[18.5rem_minmax(0,1fr)] xl:grid-cols-[18.5rem_minmax(0,1fr)_20rem] min-[1400px]:grid-cols-[20rem_minmax(0,1fr)_22rem]">
              <div className={`${tab === "inbox" ? "block" : "hidden"} min-h-0 border-line lg:block lg:border-r`}>
                <Inbox requests={requests} selectedId={selectedId} onSelect={select} filters={filters} setFilters={setFilters}
                  scopeLabel={isReviewer ? "Workspace queue" : "Your session"}
                  scopeHelp={isReviewer ? "Requests in this workspace's real queue. Changes here are visible to other reviewers." : "Requests you created in your private demo sandbox. Only this browser session can see them; Reset my demo clears them."}
                  loading={loading} query={query} />
              </div>
              <div className={`${tab === "request" ? "block" : "hidden"} min-h-0 lg:block`}>
                {running ? <Processing label={running} />
                  : detail ? (
                  <RequestPane
                    key={detail.id + (detail.proposal?.current_version ?? 0) + detail.state}
                    detail={detail} groups={ws?.ticket_groups ?? []} busy={busy} busyAction={busyAction}
                    onOpenDetails={() => setDrawer(true)}
                    onCite={cite}
                    onRun={() => act("run", () => api.run(slug, detail.id),
                      (d) => d.state === "awaiting_review" ? "Proposal ready for review." : null, target)}
                    onEdit={(changes) => act("edit", () => api.edit(slug, detail.id, { base_version: detail.proposal!.current_version, ...changes }),
                      (d) => `Saved version ${d.proposal?.current_version}. It needs a new approval.`, target)}
                    onApprove={() => act("approve", () => api.approve(slug, detail.id, detail.proposal!.version.id, detail.proposal!.version.action_hash), outcome, target)}
                    onReject={(reason) => act("reject", () => api.reject(slug, detail.id, detail.proposal!.version.id, reason), () => "Proposal rejected. No ticket was changed.", target)}
                    onRetry={() => act("retry", () => api.retry(slug, detail.id), outcome, target)}
                    onEscalateInternal={() => act("escalate", () => api.escalateInternal(slug, detail.id), outcome, target)}
                  />
                ) : <EmptyRequest scenarios={scenarios} busy={busy} onRun={runScenario} />}
              </div>
              {drawer && detail && <div aria-hidden className="fixed inset-0 z-30 hidden bg-fg/25 lg:block xl:hidden" onClick={() => setDrawer(false)} />}
              <div className={`${tab === "details" ? "flex" : "hidden"} min-h-0 flex-col border-line xl:flex xl:border-l ${drawer && detail
                ? "anim-sheet lg:fixed lg:inset-y-0 lg:right-0 lg:z-40 lg:flex lg:w-[22rem] lg:bg-canvas lg:shadow-sheet xl:static xl:z-auto xl:w-auto xl:shadow-none"
                : "lg:hidden"}`}>
                <div className="hidden shrink-0 items-center justify-between border-b border-line bg-surface px-4 py-2 lg:flex xl:hidden">
                  <span className="text-ui font-semibold text-fg">Details</span>
                  <IconButton icon={X} label="Close details" onClick={() => setDrawer(false)} />
                </div>
                <div className="min-h-0 flex-1">
                  <EvidencePane detail={running ? null : detail} onCite={cite} />
                </div>
              </div>
            </main>
          </>
        )}
      </div>

      {passage && <PassageModal passage={passage} onClose={() => setPassage(null)} />}
      {dialog === "login" && <LoginDialog onClose={() => setDialog(null)} onDone={async () => { setSelectedId(null); await loadMeta(); await loadRequests(); }} />}
      {dialog === "ai" && slug && <AiStatusDialog ws={slug} onClose={() => setDialog(null)} />}
      {dialog === "new" && slug && meta && <NewRequestDialog ws={slug} mode={meta.effective_mode} onClose={() => setDialog(null)} onCreated={async (id) => { select(id); await loadRequests(); }} />}
    </div>
  );
}
