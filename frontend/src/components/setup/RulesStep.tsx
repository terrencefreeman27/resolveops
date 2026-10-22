import { useCallback, useEffect, useState } from "react";
import { api, type Rule, type RuleIn } from "../../api";
import { Button } from "../ui";
import { Alert, Field, StepHeader, field } from "./common";

const CATEGORY_LABEL: Record<string, string> = { access: "Access", billing: "Billing", product_issue: "Product issue" };

function describe(r: Rule) {
  const c = r.condition;
  const parts = [
    c.categories?.length ? `category is ${c.categories.map((x) => CATEGORY_LABEL[x] ?? x).join(" or ")}` : "",
    c.keywords_any?.length ? `message mentions ${c.keywords_any.map((k) => `"${k}"`).join(", ")}` : "",
    c.plans_any?.length ? `plan is ${c.plans_any.join(" or ")}` : "",
  ].filter(Boolean);
  const then = r.outcome.next_action === "escalate" ? `escalate to ${r.outcome.group} (${r.outcome.priority})` : r.outcome.note ?? "human handling";
  return `If ${parts.join(" and ")}, ${then}.`;
}

export function RulesStep({ ws, onNext }: { ws: string; onNext: () => void }) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [form, setForm] = useState<RuleIn>({ name: "", categories: [], keywords_any: [], plans_any: [], action: "escalate", group: "", priority: "normal" });
  const [keywords, setKeywords] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await api.rules(ws);
    setRules(r.rules); setGroups(r.ticket_groups);
    setForm((f) => ({ ...f, group: f.group || r.ticket_groups[0] }));
  }, [ws]);
  useEffect(() => { load().catch((e) => setMsg({ tone: "error", text: e.message })); }, [load]);

  const stale = (n: number) => (n ? ` ${n} pending proposal(s) marked stale because their matching rules changed.` : "");

  return (
    <section>
      <StepHeader n={4} title="Escalation rules">
        Rules are evaluated by application code, not by the model. A matching escalation rule always wins: the proposal escalates to the rule's group and priority. Changing rules re-checks pending proposals and marks any whose matching rules changed as stale.
      </StepHeader>
      <ul className="mb-5 space-y-2" data-testid="rule-list">
        {rules.length === 0 && <li className="text-sm text-zinc-500">No rules yet.</li>}
        {rules.map((r) => (
          <li key={r.id} className="flex flex-wrap items-start justify-between gap-2 rounded-md px-3 py-2 ring-1 ring-zinc-200" data-testid="rule">
            <div><p className="text-sm font-medium text-zinc-900">{r.name}{!r.enabled && <span className="ml-1 text-xs font-normal text-zinc-500">(disabled)</span>}</p><p className="text-sm text-zinc-600">{describe(r)}</p></div>
            <div className="flex gap-1">
              <Button variant="ghost" onClick={async () => {
                const body = { name: r.name, description: r.description, categories: r.condition.categories ?? [], keywords_any: r.condition.keywords_any ?? [],
                  plans_any: r.condition.plans_any ?? [], action: (r.outcome.next_action === "escalate" ? "escalate" : "note") as RuleIn["action"],
                  group: r.outcome.group ?? null, priority: r.outcome.priority ?? "normal", note: r.outcome.note ?? null, enabled: !r.enabled };
                try { const x = await api.updateRule(ws, r.id, body); setMsg({ tone: "ok", text: `Rule ${body.enabled ? "enabled" : "disabled"}.${stale(x.proposals_marked_stale)}` }); await load(); }
                catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
              }}>{r.enabled ? "Disable" : "Enable"}</Button>
              <Button variant="ghost" onClick={async () => {
                try { const x = await api.deleteRule(ws, r.id); setMsg({ tone: "ok", text: `Rule deleted.${stale(x.proposals_marked_stale)}` }); await load(); }
                catch (e) { setMsg({ tone: "error", text: (e as Error).message }); }
              }}>Delete</Button>
            </div>
          </li>
        ))}
      </ul>

      <form className="grid max-w-2xl gap-4 rounded-lg bg-zinc-50 p-4 ring-1 ring-zinc-200" data-testid="rule-form" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setMsg(null);
        const body = { ...form, keywords_any: keywords.split(",").map((k) => k.trim()).filter(Boolean) };
        try { const x = await api.createRule(ws, body); setMsg({ tone: "ok", text: `Rule "${x.name}" added.${stale(x.proposals_marked_stale)}` }); setKeywords(""); setForm({ ...form, name: "" }); await load(); }
        catch (err) { setMsg({ tone: "error", text: (err as Error).message }); } finally { setBusy(false); }
      }}>
        <p className="text-sm font-semibold text-zinc-900">Add a rule</p>
        <Field label="Rule name"><input className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} data-testid="rule-name" /></Field>
        <Field label="Message mentions any of" hint="Comma-separated, case-insensitive."><input className={field} value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="refund, chargeback" data-testid="rule-keywords" /></Field>
        <fieldset className="flex flex-wrap gap-3 text-sm text-zinc-700"><legend className="mb-1 text-sm font-medium">Only for categories (optional)</legend>
          {Object.entries(CATEGORY_LABEL).map(([k, label]) => (
            <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={form.categories.includes(k)} onChange={(e) => setForm({ ...form, categories: e.target.checked ? [...form.categories, k] : form.categories.filter((x) => x !== k) })} />{label}</label>
          ))}
        </fieldset>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Escalate to group"><select className={field} value={form.group ?? ""} onChange={(e) => setForm({ ...form, group: e.target.value })} data-testid="rule-group">{groups.map((g) => <option key={g}>{g}</option>)}</select></Field>
          <Field label="Priority"><select className={field} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} data-testid="rule-priority">{["low", "normal", "high", "urgent"].map((p) => <option key={p}>{p}</option>)}</select></Field>
        </div>
        {msg && <Alert tone={msg.tone} testId={msg.tone === "ok" ? "setup-ok" : "setup-error"}>{msg.text}</Alert>}
        <div><Button type="submit" variant="primary" disabled={busy} data-testid="rule-save">Add rule</Button></div>
      </form>
      <div className="mt-6"><Button variant="primary" onClick={onNext} data-testid="setup-next">Continue</Button></div>
    </section>
  );
}
