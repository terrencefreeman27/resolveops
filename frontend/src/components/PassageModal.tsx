import { useEffect, useRef } from "react";
import type { Passage } from "../api";
import { Button, Tag } from "./ui";

export function PassageModal({ passage, onClose }: { passage: Passage; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const mark = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    mark.current?.scrollIntoView({ block: "center" });
  }, []);
  const idx = passage.document_content.indexOf(passage.text);
  const before = idx >= 0 ? passage.document_content.slice(0, idx) : "";
  const after = idx >= 0 ? passage.document_content.slice(idx + passage.text.length) : "";
  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-[min(48rem,calc(100vw-2rem))] rounded-xl p-0 shadow-xl backdrop:bg-zinc-900/40" data-testid="passage-modal">
      <div className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4">
        <div>
          <p className="text-xs text-zinc-500">{passage.doc_slug}, version {passage.version}</p>
          <h2 className="text-base font-semibold text-zinc-900">{passage.doc_title}: {passage.section}</h2>
          <div className="mt-1 flex gap-1.5">
            <span data-testid="passage-version-status"><Tag tone={passage.active ? "teal" : "amber"}>{passage.active ? "Active version"
              : passage.document_status === "deleted" ? "Document deleted; showing the cited version"
              : passage.current_version && passage.current_version !== passage.version ? `Superseded by v${passage.current_version}; showing the cited v${passage.version}`
              : `Not active (${passage.version_status})`}</Tag></span>
          </div>
        </div>
        <Button variant="ghost" onClick={() => ref.current?.close()} aria-label="Close passage">Close</Button>
      </div>
      <div className="max-h-[65vh] overflow-y-auto whitespace-pre-wrap px-5 py-4 font-mono text-[13px] leading-relaxed text-zinc-500">
        {idx >= 0 ? (
          <>{before}<mark ref={mark} className="rounded bg-teal-50 text-zinc-900 ring-1 ring-teal-200">{passage.text}</mark>{after}</>
        ) : <mark className="bg-teal-50 text-zinc-900">{passage.text}</mark>}
      </div>
    </dialog>
  );
}
