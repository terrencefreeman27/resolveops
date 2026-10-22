import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Meta, type Passage, type RequestDetail, type RequestSummary } from "./api";
import { LoginDialog, NewRequestDialog } from "./components/Dialogs";
import { EvidencePane } from "./components/EvidencePane";
import { Inbox, type Filters } from "./components/Inbox";
import { PassageModal } from "./components/PassageModal";
import { RequestPane } from "./components/RequestPane";
import { Button } from "./components/ui";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [filters, setFilters] = useState<Filters>({ state: "", category: "" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"login" | "new" | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);

  const ws = meta?.workspaces[0];
  const slug = ws?.slug ?? "";

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
  useEffect(() => { loadRequests(); }, [loadRequests]);
  useEffect(() => {
    if (!slug || !selectedId) { setDetail(null); return; }
    api.request(slug, selectedId).then(setDetail).catch((e: ApiError) => {
      setDetail(null);
      if (e.status === 404) setSelectedId(null); else setError(e.message);
    });
  }, [slug, selectedId]);

  async function act(fn: () => Promise<RequestDetail>, okMessage?: (d: RequestDetail) => string | null) {
    setBusy(true); setError(null); setNotice(null);
    try {
      const d = await fn();
      setDetail(d);
      setSelectedId(d.id);
      const msg = okMessage?.(d);
      if (msg) setNotice(msg);
      await loadRequests();
      return true;
    } catch (e) {
      setError((e as Error).message);
      if (selectedId) api.request(slug, selectedId).then(setDetail).catch(() => undefined);
      return false;
    } finally { setBusy(false); }
  }

  const outcome = (d: RequestDetail) =>
    d.state === "completed" ? (d.tickets.length ? `Approved. Ticket ${d.tickets.map((t) => t.number).join(", ")} recorded.` : "Approved. Reply draft recorded; no ticket change.")
    : d.state === "failed" ? "Execution failed. Details are in the timeline; you can retry safely." : null;

  if (fatal) {
    return <main className="grid min-h-[100dvh] place-items-center p-6 text-center"><div><h1 className="text-lg font-semibold">ResolveOps is not reachable</h1><p className="mt-1 text-sm text-zinc-600">{fatal}</p><Button className="mt-4" onClick={() => { setFatal(null); loadMeta(); }}>Try again</Button></div></main>;
  }

  const isReviewer = !!meta?.reviewer;
  return (
    <div className="flex flex-col xl:h-[100dvh]">
      <div className={`px-4 py-1.5 text-center text-sm font-medium ${meta?.mode === "live" ? "bg-teal-800 text-white" : "bg-amber-300 text-amber-950"}`} data-testid="mode-banner">
        {meta ? (meta.mode === "demo"
          ? "Demo mode: Simulated AI. Outputs are deterministic fixtures on synthetic data; tickets are internal only."
          : `Live mode: ${meta.provider_label}`) : "Connecting"}
      </div>

      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-zinc-200 bg-white px-4 py-2.5">
        <div className="mr-2">
          <p className="text-sm font-semibold tracking-tight">ResolveOps</p>
          <p className="text-xs text-zinc-500">{ws?.name ?? ""} <span className="text-zinc-400">(fictional company)</span></p>
        </div>
        <div className="flex flex-wrap items-center gap-2" aria-label="Demo scenarios">
          {ws?.demo_scenarios.map((s) => (
            <Button key={s.key} title={s.description} disabled={busy} data-testid={`scenario-${s.key}`}
              onClick={() => act(() => api.runScenario(slug, s.key), (d) => d.state === "awaiting_review" ? `${s.label}: proposal ready for review.` : null)}>
              {s.label}
            </Button>
          ))}
          <Button variant="ghost" onClick={() => setDialog("new")} disabled={!slug}>New request</Button>
        </div>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <span className="hidden text-zinc-600 sm:inline" data-testid="scope">{isReviewer ? `${meta?.reviewer?.name}, reviewer` : "Visitor, private demo sandbox"}</span>
          {!isReviewer && (
            <Button variant="ghost" disabled={busy} data-testid="reset-demo" onClick={async () => {
              setBusy(true);
              try { await api.resetDemo(); setSelectedId(null); setNotice("Your demo session was reset. Other visitors are unaffected."); await loadRequests(); }
              catch (e) { setError((e as Error).message); } finally { setBusy(false); }
            }}>Reset my demo</Button>
          )}
          {isReviewer
            ? <Button onClick={async () => { await api.logout(); setSelectedId(null); await loadMeta(); }}>Sign out</Button>
            : <Button onClick={() => setDialog("login")}>Reviewer sign-in</Button>}
        </div>
      </header>

      {(error || notice) && (
        <div className={`flex items-center justify-between gap-4 px-4 py-2 text-sm ${error ? "bg-red-50 text-red-800" : "bg-teal-50 text-teal-900"}`} role={error ? "alert" : "status"} data-testid={error ? "error" : "notice"}>
          <span>{error ?? notice}</span>
          <button className="text-xs underline" onClick={() => { setError(null); setNotice(null); }}>Dismiss</button>
        </div>
      )}

      <main className="grid flex-1 grid-cols-1 lg:grid-cols-[19rem_minmax(0,1fr)] xl:min-h-0 xl:grid-cols-[19rem_minmax(0,1fr)_21rem]">
        <div className="max-h-[45dvh] min-h-0 overflow-hidden lg:max-h-none [&>aside]:h-full">
          <Inbox requests={requests} selectedId={selectedId} onSelect={setSelectedId} filters={filters} setFilters={setFilters}
            scopeLabel={isReviewer ? "Workspace queue" : "Your demo session"} loading={loading} />
        </div>
        {detail ? (
          <RequestPane
            key={detail.id + (detail.proposal?.current_version ?? 0)}
            detail={detail} groups={ws?.ticket_groups ?? []} busy={busy}
            onCite={async (id) => { try { setPassage(await api.passage(slug, id)); } catch (e) { setError((e as Error).message); } }}
            onRun={() => act(() => api.run(slug, detail.id))}
            onEdit={(changes) => act(() => api.edit(slug, detail.id, { base_version: detail.proposal!.current_version, ...changes }),
              (d) => `Saved version ${d.proposal?.current_version}. It needs a new approval.`)}
            onApprove={() => act(() => api.approve(slug, detail.id, detail.proposal!.version.id, detail.proposal!.version.action_hash), outcome)}
            onReject={(reason) => act(() => api.reject(slug, detail.id, detail.proposal!.version.id, reason), () => "Proposal rejected.")}
            onRetry={() => act(() => api.retry(slug, detail.id), outcome)}
          />
        ) : (
          <section className="grid place-items-center bg-white p-10 text-center">
            <div className="max-w-sm">
              <h1 className="text-lg font-semibold text-zinc-900">Pick a request or run a demo scenario</h1>
              <p className="mt-2 text-sm text-zinc-600">Each scenario runs the real workflow: tools look up the authorized account, retrieval finds documentation, and nothing changes until you approve.</p>
            </div>
          </section>
        )}
        <div className="lg:col-span-2 xl:col-span-1 xl:min-h-0 [&>aside]:h-full">
          <EvidencePane detail={detail} onCite={async (id) => { try { setPassage(await api.passage(slug, id)); } catch (e) { setError((e as Error).message); } }} />
        </div>
      </main>

      {passage && <PassageModal passage={passage} onClose={() => setPassage(null)} />}
      {dialog === "login" && <LoginDialog onClose={() => setDialog(null)} onDone={async () => { setSelectedId(null); await loadMeta(); await loadRequests(); }} />}
      {dialog === "new" && slug && meta && <NewRequestDialog ws={slug} mode={meta.mode} onClose={() => setDialog(null)} onCreated={async (id) => { setSelectedId(id); await loadRequests(); }} />}
    </div>
  );
}
