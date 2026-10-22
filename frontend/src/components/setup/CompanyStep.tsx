import { useEffect, useState } from "react";
import { api, type CompanyIn, type Workspace } from "../../api";
import { Button } from "../ui";
import { Alert, Field, StepHeader, field } from "./common";

const EMPTY: CompanyIn = { name: "", tagline: "", industry: "", support_hours: "", support_signature: "", ticket_groups: ["Support", "Billing", "Engineering"] };

export function CompanyStep({ ws, onCreated, onSaved }: { ws: Workspace | null; onCreated: (slug: string) => Promise<void>; onSaved: () => Promise<void> }) {
  const [creating, setCreating] = useState(!ws);
  const [form, setForm] = useState<CompanyIn>(EMPTY);
  const [groups, setGroups] = useState(EMPTY.ticket_groups.join(", "));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "error" | "ok"; text: string } | null>(null);

  useEffect(() => {
    if (!ws || creating) { setForm(EMPTY); setGroups(EMPTY.ticket_groups.join(", ")); return; }
    api.settings(ws.slug).then((s) => {
      const p = s.profile ?? {};
      setForm({ name: s.name, tagline: p.tagline ?? "", industry: p.industry ?? "", support_hours: p.support_hours ?? "",
        support_signature: p.support_signature ?? "", ticket_groups: s.settings.ticket_groups });
      setGroups(s.settings.ticket_groups.join(", "));
    }).catch((e) => setMsg({ tone: "error", text: e.message }));
  }, [ws, creating]);

  const set = (k: keyof CompanyIn) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <section>
      <StepHeader n={1} title={creating ? "Create a workspace" : `Company details for ${ws?.name}`}>
        Everything company-specific (profile, documents, escalation rules, ticket destinations) is stored per workspace. You become the workspace's first reviewer; other reviewers cannot see it.
      </StepHeader>
      <form className="grid max-w-2xl gap-4" data-testid="company-form" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setMsg(null);
        const body = { ...form, ticket_groups: groups.split(",").map((g) => g.trim()).filter(Boolean) };
        try {
          if (creating) { const s = await api.createWorkspace(body); setMsg({ tone: "ok", text: `Workspace "${s.name}" created.` }); await onCreated(s.slug); setCreating(false); }
          else if (ws) { await api.updateCompany(ws.slug, body); await onSaved(); setMsg({ tone: "ok", text: "Company details saved." }); }
        } catch (err) { setMsg({ tone: "error", text: (err as Error).message }); } finally { setBusy(false); }
      }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Company name"><input className={field} value={form.name} onChange={set("name")} required minLength={2} maxLength={120} data-testid="company-name" /></Field>
          <Field label="Industry"><input className={field} value={form.industry} onChange={set("industry")} maxLength={120} placeholder="B2B SaaS — scheduling" /></Field>
        </div>
        <Field label="What the company does"><input className={field} value={form.tagline} onChange={set("tagline")} maxLength={300} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Support hours"><input className={field} value={form.support_hours} onChange={set("support_hours")} maxLength={120} placeholder="Mon–Fri 09:00–17:00" /></Field>
          <Field label="Reply signature" hint="Used to sign drafted replies."><input className={field} value={form.support_signature} onChange={set("support_signature")} maxLength={120} placeholder={`${form.name || "Company"} Support`} /></Field>
        </div>
        <Field label="Ticket groups" hint="Comma-separated. Escalations and tickets may only go to these groups.">
          <input className={field} value={groups} onChange={(e) => setGroups(e.target.value)} required data-testid="company-groups" />
        </Field>
        {msg && <Alert tone={msg.tone} testId={msg.tone === "ok" ? "setup-ok" : "setup-error"}>{msg.text}</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={busy} data-testid="company-save">{creating ? "Create workspace" : "Save details"}</Button>
          {ws && <Button type="button" variant="ghost" onClick={() => { setCreating(!creating); setMsg(null); }}>{creating ? `Edit ${ws.name} instead` : "Create another workspace"}</Button>}
        </div>
      </form>
    </section>
  );
}
