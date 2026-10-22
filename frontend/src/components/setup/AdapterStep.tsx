import { useEffect, useState } from "react";
import { api, type Adapter } from "../../api";
import { Button } from "../ui";
import { Alert, StepHeader } from "./common";

export function AdapterStep({ ws, onNext }: { ws: string; onNext: () => void }) {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [selected, setSelected] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  useEffect(() => { api.adapters(ws).then((r) => { setAdapters(r.adapters); setSelected(r.selected); }).catch((e) => setMsg({ tone: "error", text: e.message })); }, [ws]);
  return (
    <section>
      <StepHeader n={5} title="Ticket adapter">Approved actions create or update tickets through one adapter per workspace. Visitor sandboxes always use the internal adapter.</StepHeader>
      <fieldset className="grid max-w-2xl gap-2" data-testid="adapter-list">
        <legend className="sr-only">Ticket adapter</legend>
        {adapters.map((a) => (
          <label key={a.name} className={`flex items-start gap-3 rounded-lg p-3 ring-1 ${selected === a.name ? "ring-teal-600" : "ring-zinc-200"} ${a.available ? "cursor-pointer" : "cursor-not-allowed opacity-70"}`}>
            <input type="radio" name="adapter" className="mt-1" value={a.name} checked={selected === a.name} disabled={!a.available} data-testid={`adapter-${a.name}`}
              onChange={async () => {
                try { const r = await api.selectAdapter(ws, a.name); setSelected(r.selected); setMsg({ tone: "ok", text: `${a.label} selected.` }); }
                catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
              }} />
            <span><span className="block text-sm font-medium text-zinc-900">{a.label} {!a.available && <span className="ml-1 rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600">Not configured</span>}</span>
              <span className="block text-sm text-zinc-600">{a.detail}</span></span>
          </label>
        ))}
      </fieldset>
      {msg && <div className="mt-4 max-w-2xl"><Alert tone={msg.tone} testId={msg.tone === "ok" ? "setup-ok" : "setup-error"}>{msg.text}</Alert></div>}
      <div className="mt-6"><Button variant="primary" onClick={onNext} data-testid="setup-next">Continue</Button></div>
    </section>
  );
}
