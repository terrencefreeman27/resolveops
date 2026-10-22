import { useState } from "react";
import { api, type TestResult } from "../../api";
import { Button, Tag } from "../ui";
import { Alert, Field, StepHeader, field } from "./common";

export function TestStep({ ws }: { ws: string }) {
  const [text, setText] = useState("");
  const [category, setCategory] = useState("billing");
  const [plan, setPlan] = useState("");
  const [res, setRes] = useState<TestResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ec = res?.evidence_check;
  return (
    <section>
      <StepHeader n={6} title="Test a sample support request">
        Runs the deterministic parts of the workflow against this workspace: retrieval over its active documents, the evidence check, and its escalation rules. No AI model is called and nothing is stored.
      </StepHeader>
      <form className="grid max-w-2xl gap-4" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setErr(null);
        try { setRes(await api.testRequest(ws, text, category, plan)); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
      }}>
        <Field label="Customer message"><textarea className={`${field} min-h-24`} value={text} onChange={(e) => setText(e.target.value)} required minLength={3} maxLength={4000} data-testid="test-text" /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category"><select className={field} value={category} onChange={(e) => setCategory(e.target.value)}><option value="access">Access</option><option value="billing">Billing</option><option value="product_issue">Product issue</option></select></Field>
          <Field label="Customer plan (optional)" hint="Only used by plan-specific rules."><input className={field} value={plan} onChange={(e) => setPlan(e.target.value)} maxLength={32} /></Field>
        </div>
        {err && <Alert tone="error">{err}</Alert>}
        <div><Button type="submit" variant="primary" disabled={busy} data-testid="test-run">Run test</Button></div>
      </form>

      {res && ec && (
        <div className="mt-6 grid max-w-3xl gap-4" data-testid="test-result">
          <div className="rounded-lg p-4 ring-1 ring-zinc-200">
            <div className="flex flex-wrap items-center gap-2">
              <Tag tone={ec.status === "sufficient" ? "teal" : "amber"}>Evidence: {ec.status}</Tag>
              <span className="text-xs text-zinc-500">threshold {ec.threshold.toFixed(2)} · best match {ec.best_score?.toFixed(2) ?? "none"} · {ec.relevant_passages} relevant passage(s)</span>
            </div>
            <p className="mt-2 text-sm text-zinc-900" data-testid="test-outcome"><span className="font-medium">Allowed outcome:</span> {res.allowed_outcome}</p>
            {res.rule_hits.map((h) => <p key={h.key} className="mt-1 text-sm text-zinc-700">Rule matched: <span className="font-medium">{h.name}</span> — {h.effect}</p>)}
            {ec.conflicts.map((c) => <p key={c.key} className="mt-1 text-sm text-amber-800">Conflict on {c.key}: {c.values.map((v) => `${v.doc_title} v${v.version} says "${v.value}"`).join("; ")}</p>)}
            <p className="mt-2 text-xs text-zinc-500">{res.note}</p>
          </div>
          <ol className="space-y-2">
            {res.passages.map((p) => (
              <li key={p.chunk_id} className="rounded-md px-3 py-2 ring-1 ring-zinc-200" data-testid="test-passage">
                <p className="text-sm font-medium text-zinc-900">{p.doc_title} v{p.version}: {p.section} <span className={`ml-1 text-xs font-normal ${p.relevant ? "text-teal-700" : "text-zinc-400"}`}>score {p.score.toFixed(2)}{p.relevant ? "" : " (below threshold)"}</span></p>
                <p className="mt-0.5 text-sm text-zinc-600">{p.excerpt}</p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
