import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Doc, type DocDetail, type DocLimits } from "../../api";
import { Button } from "../ui";
import { Alert, IMPORT_STYLE, Pill, StepHeader } from "./common";

const ACCEPT = ".md,.markdown,.txt,text/markdown,text/plain";

function latest(d: Doc) { return d.versions[0]; }

export function DocumentsStep({ ws, mode, onNext }: { ws: string; mode: "import" | "review"; onNext: () => void }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [limits, setLimits] = useState<DocLimits | null>(null);
  const [open, setOpen] = useState<DocDetail | null>(null);
  const [msg, setMsg] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const r = await api.documents(ws);
    setDocs(r.documents); setLimits(r.limits);
    return r.documents;
  }, [ws]);
  useEffect(() => { load().catch((e) => setMsg({ tone: "error", text: e.message })); }, [load]);
  // Poll while any import is still pending/processing.
  const inFlight = docs.some((d) => ["pending", "processing"].includes(latest(d)?.import_status));
  useEffect(() => {
    if (!inFlight) return;
    const t = setInterval(() => load().catch(() => undefined), 800);
    return () => clearInterval(t);
  }, [inFlight, load]);

  async function send(files: FileList | null, replaceId?: string) {
    if (!files?.length) return;
    setBusy(true); setMsg(null);
    const done: string[] = [];
    try {
      for (const f of Array.from(files)) {
        const text = await f.text();
        if (replaceId) await api.replaceDocument(ws, replaceId, f.name, text); else await api.importDocument(ws, f.name, text);
        done.push(f.name);
      }
      setMsg({ tone: "ok", text: `${replaceId ? "Replacement" : "Import"} started for ${done.join(", ")}.` });
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
      const list = await load();
      if (replaceId) { const d = list.find((x) => x.id === replaceId); if (d) setTimeout(() => view(d.id), 900); }
    }
  }

  async function view(id: string, version?: number) {
    try { setOpen(await api.document(ws, id, version)); } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
  }

  return (
    <section>
      {mode === "import" ? (
        <StepHeader n={2} title="Import documentation">
          Import your help-center articles and policies as files. {limits?.note ?? "Only Markdown (.md) and plain-text (.txt) files can be imported."} PDF, Word and HTML are not supported. Markdown is split into sections at each "##" heading; plain text is split into paragraphs.
        </StepHeader>
      ) : (
        <StepHeader n={3} title="Review import status and contents">
          Each import is a numbered version. Replacing a document supersedes the old version and removes it from retrieval; deleting removes the document from retrieval. Pending proposals that relied on a replaced or deleted version become stale.
        </StepHeader>
      )}

      {mode === "import" && (
        <div className="mb-5 rounded-lg border border-dashed border-line-strong p-4">
          <div className="flex flex-wrap items-center gap-3">
            <input ref={fileRef} type="file" accept={ACCEPT} multiple className="sr-only" data-testid="doc-file" onChange={(e) => { send(e.target.files); e.target.value = ""; }} />
            <Button variant="primary" disabled={busy} onClick={() => fileRef.current?.click()}>Choose .md or .txt files</Button>
            <p className="text-sm text-fg-muted">
              Supported: <span className="font-medium">.md, .markdown, .txt</span>
              {limits && <> · up to {(limits.max_upload_bytes / 1000).toLocaleString("en-US")} KB each · {limits.max_documents} documents per workspace</>}
            </p>
          </div>
          <p className="mt-2 text-xs text-fg-subtle">Optional: mark a policy fact inside a section with <code className="rounded bg-sunken px-1">{"<!-- policy refunds.window_days: 30 -->"}</code>. If two current documents state different values for the same key, ResolveOps escalates instead of answering.</p>
        </div>
      )}
      {msg && <div className="mb-4"><Alert tone={msg.tone} testId={msg.tone === "ok" ? "setup-ok" : "setup-error"}>{msg.text}</Alert></div>}

      <div className="overflow-x-auto rounded-lg ring-1 ring-line">
        <table className="w-full min-w-[36rem] text-left text-sm" data-testid="doc-table">
          <thead className="bg-canvas text-xs text-fg-subtle"><tr><th className="px-3 py-2 font-medium">Document</th><th className="px-3 py-2 font-medium">Version</th><th className="px-3 py-2 font-medium">Import status</th><th className="px-3 py-2 font-medium">Lifecycle</th><th className="px-3 py-2" /></tr></thead>
          <tbody className="divide-y divide-line">
            {docs.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-fg-subtle">No documents yet.</td></tr>}
            {docs.map((d) => {
              const v = latest(d);
              return (
                <tr key={d.id} data-testid="doc-row" data-slug={d.slug}>
                  <td className="px-3 py-2"><p className="font-medium text-fg">{d.title}</p><p className="text-xs text-fg-subtle">{v?.filename ?? d.slug}</p></td>
                  <td className="px-3 py-2 tabular-nums">v{v?.version}</td>
                  <td className="px-3 py-2"><Pill className={IMPORT_STYLE[v?.import_status] ?? ""} testId="import-status">{v?.import_status}</Pill>{v?.import_error && <p className="mt-0.5 text-xs text-danger">{v.import_error}</p>}</td>
                  <td className="px-3 py-2 text-fg-muted">{d.status === "deleted" ? "deleted" : v?.status}</td>
                  <td className="px-3 py-2 text-right"><Button variant="ghost" onClick={() => view(d.id)} data-testid="doc-view">View</Button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {open && (
        <article className="mt-5 rounded-lg ring-1 ring-line" data-testid="doc-detail">
          <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div>
              <h3 className="text-base font-semibold text-fg">{open.title}</h3>
              <p className="text-xs text-fg-subtle">id {open.id.slice(0, 8)} · showing v{open.version.version} ({open.version.status}) · {open.version.format}</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {open.versions.map((v) => (
                  <button key={v.id} onClick={() => view(open.id, v.version)} className={`rounded px-1.5 py-0.5 text-xs ${v.version === open.version.version ? "bg-accent text-white" : "bg-sunken text-fg-muted hover:bg-sunken"}`}>v{v.version} {v.status}</button>
                ))}
              </div>
            </div>
            {open.status !== "deleted" && (
              <div className="flex gap-2">
                <input ref={replaceRef} type="file" accept={ACCEPT} className="sr-only" data-testid="doc-replace-file" onChange={(e) => { send(e.target.files, open.id); e.target.value = ""; }} />
                <Button disabled={busy} onClick={() => replaceRef.current?.click()} data-testid="doc-replace">Replace…</Button>
                <Button variant="danger" disabled={busy} data-testid="doc-delete" onClick={async () => {
                  if (!confirm(`Delete "${open.title}"? It leaves retrieval immediately; pending proposals that used it become stale.`)) return;
                  try { const r = await api.deleteDocument(ws, open.id); setMsg({ tone: "ok", text: `Deleted. ${r.proposals_marked_stale} pending proposal(s) marked stale.` }); setOpen(null); await load(); }
                  catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
                }}>Delete</Button>
              </div>
            )}
          </header>
          {Object.keys(open.version.policy_facts).length > 0 && (
            <p className="border-b border-line px-4 py-2 text-xs text-fg-muted">Policy facts: {Object.entries(open.version.policy_facts).map(([k, v]) => `${k} = ${v}`).join(" · ")}</p>
          )}
          <ol className="divide-y divide-line" data-testid="doc-sections">
            {open.sections.map((s) => (
              <li key={s.chunk_id} className="px-4 py-3">
                <p className="text-sm font-medium text-fg">{s.section} {!s.active && <span className="ml-1 text-xs font-normal text-warn">(not in retrieval)</span>}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-fg-muted">{s.text}</p>
              </li>
            ))}
            {open.sections.length === 0 && <li className="px-4 py-3 text-sm text-fg-subtle">No sections ({open.version.import_status}).</li>}
          </ol>
        </article>
      )}

      <div className="mt-6"><Button variant="primary" onClick={onNext} data-testid="setup-next">Continue</Button></div>
    </section>
  );
}
