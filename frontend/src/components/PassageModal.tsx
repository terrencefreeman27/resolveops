import { useEffect, useRef } from "react";
import { FileText, X } from "lucide-react";
import type { Passage } from "../api";
import { IconButton, Tag } from "./ui";

/** The cited passage, highlighted inside its full document, in a right-hand sheet. */
export function PassageModal({ passage, onClose }: { passage: Passage; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const mark = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    mark.current?.scrollIntoView({ block: "center" });
  }, []);
  // Source documents are hard-wrapped markdown; join soft line breaks so text reflows at any width.
  // Tables, headings and list items keep their line breaks.
  const unwrap = (t: string) => t.replace(/(?<=[^\n|])\n(?=[^\n|#\-*>\s\d])/g, " ");
  const doc = unwrap(passage.document_content);
  const text = unwrap(passage.text);
  const idx = doc.indexOf(text);
  const before = idx >= 0 ? doc.slice(0, idx) : "";
  const after = idx >= 0 ? doc.slice(idx + text.length) : "";
  const status = passage.active ? "Active version"
    : passage.document_status === "deleted" ? "Document deleted; showing the cited version"
    : passage.current_version && passage.current_version !== passage.version ? `Superseded by v${passage.current_version}; showing the cited v${passage.version}`
    : `Not active (${passage.version_status})`;
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="passage-title" data-testid="passage-modal"
      onClick={(e) => { if (e.target === ref.current) ref.current?.close(); }}
      className="anim-sheet m-0 ml-auto h-[100dvh] max-h-[100dvh] w-[min(46rem,100vw)] max-w-none bg-surface p-0 shadow-sheet">
      <div className="flex h-full flex-col">
        <header className="flex items-start gap-3 border-b border-line px-5 py-4">
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-accent-soft text-accent-strong"><FileText aria-hidden className="size-4" strokeWidth={1.75} /></span>
          <div className="min-w-0 flex-1">
            <h2 id="passage-title" className="text-base font-semibold leading-snug text-fg [overflow-wrap:anywhere]">{passage.section}</h2>
            <p className="mt-0.5 text-xs text-fg-subtle [overflow-wrap:anywhere]">{passage.doc_title} · version {passage.version} · <span className="font-mono">{passage.doc_slug}</span></p>
            <div className="mt-2" data-testid="passage-version-status"><Tag tone={passage.active ? "ok" : "warn"}>{status}</Tag></div>
          </div>
          <IconButton icon={X} label="Close passage" onClick={() => ref.current?.close()} />
        </header>
        <div className="pane-scroll min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-6 py-5 font-mono text-[12.5px] leading-relaxed text-fg-subtle [overflow-wrap:anywhere]">
          {idx >= 0 ? (
            <>{before}<mark ref={mark} className="rounded-sm bg-[#d3ebe6] text-fg [box-decoration-break:clone]">{text}</mark>{after}</>
          ) : <mark className="bg-accent-soft text-fg">{text}</mark>}
        </div>
      </div>
    </dialog>
  );
}
