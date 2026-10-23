import { BookOpenText, ExternalLink, FileText, History, Ticket, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import type { RequestDetail } from "../api";
import { actorLabel, categoryLabel, humanize, humanizeInline, humanizeList } from "../labels";
import { versionNote } from "./ProposalParts";
import { Disclosure, HelpTip, timeAgo } from "./ui";

type Fact = { label: string; value: string; source: string };
type GroupKey = "subscription" | "seats" | "billing" | "product" | "history";
const GROUPS: { key: GroupKey; title: string; test: (f: Fact) => boolean }[] = [
  { key: "billing", title: "Invoices and charges", test: (f) => /invoice|payment|charge|refund|credit/i.test(f.label) },
  { key: "seats", title: "Seats and permissions", test: (f) => /^seats$|admin|user|role|member|permission|contact/i.test(f.label) },
  { key: "subscription", title: "Subscription", test: (f) => /^(plan|plan change|plan features|status|subscription)$/i.test(f.label) },
  { key: "product", title: "Product configuration", test: (f) => /connector|integration|sync|sso|configuration|service/i.test(f.label) },
  { key: "history", title: "Previous tickets", test: (f) => /ticket|conversation/i.test(f.label) },
];
/** Which account details matter first for each request category; the rest stay one click away. */
const RELEVANT: Record<string, GroupKey[]> = {
  billing: ["billing", "subscription"],
  access: ["seats", "subscription"],
  product_issue: ["product", "history"],
};

function groupFacts(facts: Fact[], category: string | null | undefined) {
  const out = GROUPS.map((g) => ({ key: g.key as GroupKey | "other", title: g.title, facts: [] as Fact[] }));
  const other: Fact[] = [];
  let account: Fact | null = null;
  for (const f of facts) {
    if (/^account$/i.test(f.label)) { account = f; continue; }
    const i = GROUPS.findIndex((g) => g.test(f));
    (i >= 0 ? out[i].facts : other).push(f);
  }
  if (other.length) out.push({ key: "other", title: "Other account details", facts: other });
  const present = out.filter((g) => g.facts.length);
  const order = RELEVANT[category ?? ""];
  if (!order) return { account, primary: present, more: [] };
  const primary = order.map((k) => present.find((g) => g.key === k)).filter((g): g is (typeof present)[number] => !!g);
  return { account, primary, more: present.filter((g) => !primary.includes(g)) };
}

function FactList({ facts }: { facts: Fact[] }) {
  return (
    <dl className="space-y-1.5">
      {facts.map((f) => (
        <div key={f.label} className="grid grid-cols-[minmax(5.5rem,38%)_minmax(0,1fr)] gap-x-3 text-ui" title={`Source: ${humanize(f.source)}`}>
          <dt className="text-fg-subtle [overflow-wrap:anywhere]">{factLabel(f)}</dt>
          <dd className="text-fg [overflow-wrap:anywhere]">{f.label === "Plan features" ? humanizeList(f.value) : humanizeInline(f.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** "Invoice INV-2026-110421" → label "Invoice", id "INV-2026-110421"; "Connector Snowflake (prod)" → "Snowflake (prod)". */
function factLabel(f: Fact): ReactNode {
  const inv = f.label.match(/^Invoice (\S+)$/);
  if (inv) return <span className="font-mono text-2xs">{inv[1]}</span>;
  const con = f.label.match(/^Connector (.+)$/);
  if (con) return con[1];
  return f.label;
}

function CustomerFacts({ facts, category }: { facts: Fact[]; category: string | null | undefined }) {
  const g = groupFacts(facts, category);
  return (
    <div className="space-y-3 pb-1 pt-1">
      {g.account && <p className="text-ui font-medium text-fg [overflow-wrap:anywhere]" title={`Source: ${humanize(g.account.source)}`}>{g.account.value}</p>}
      {g.more.length > 0 && g.primary.length > 0 && <p className="text-xs font-medium text-accent-strong" data-testid="facts-relevance">Relevant to this {categoryLabel(category).toLowerCase()} request</p>}
      <div className="space-y-3" data-testid="facts-primary">
        {g.primary.map((grp) => (
          <div key={grp.key} data-group={grp.key}>
            <h4 className="pb-1 text-2xs font-semibold text-fg-subtle">{grp.title}</h4>
            <FactList facts={grp.facts} />
          </div>
        ))}
      </div>
      {g.more.length > 0 && (
        <div className="border-t border-line pt-2" data-testid="facts-more">
          <p className="pb-0.5 text-2xs font-semibold text-fg-subtle">More account details</p>
          {g.more.map((grp) => (
            <Disclosure key={grp.key} title={<span className="text-xs">{grp.title}</span>} meta={String(grp.facts.length)} className="text-xs" testId={`facts-group-${grp.key}`}>
              <div className="pb-1.5 pl-6"><FactList facts={grp.facts} /></div>
            </Disclosure>
          ))}
        </div>
      )}
    </div>
  );
}

function Section({ title, icon: Icon, count, help, children, defaultOpen = true, testId }: {
  title: string; icon: typeof FileText; count?: number; help?: ReactNode; children: ReactNode; defaultOpen?: boolean; testId?: string;
}) {
  return (
    <section className="relative border-b border-line px-4 py-3 last:border-b-0" data-testid={testId}>
      <Disclosure defaultOpen={defaultOpen} icon={Icon} className={help ? "[&>summary]:pr-7" : ""}
        title={<span className="inline-flex items-center gap-1.5">{title}{count != null && <span className="text-xs font-normal tabular-nums text-fg-subtle">{count}</span>}</span>}>
        {children}
      </Disclosure>
      {help && <div className="absolute right-4 top-[1.0625rem]">{help}</div>}
    </section>
  );
}

export function EvidencePane({ detail: d, onCite }: { detail: RequestDetail | null; onCite: (id: string) => void }) {
  if (!d) {
    return (
      <aside className="hidden h-full bg-canvas px-5 py-6 xl:block" aria-label="Request details">
        <p className="text-ui text-fg-subtle">Account facts, sources and tickets for the selected request appear here.</p>
      </aside>
    );
  }
  const c = d.proposal?.version.content;
  type Entry = { at: string; text: string; detail?: string; tone: "neutral" | "warn" | "ok" | "danger"; link?: { href: string; label: string } };
  const history: Entry[] = [
    ...(d.proposal?.versions ?? []).map((v) => ({ at: v.created_at, text: `Version ${v.version} by ${actorLabel(v.author)}${v.edit_note ? ` (${v.edit_note})` : ""}`, tone: "neutral" as const })),
    ...d.approvals.map((a) => ({ at: a.created_at, text: `${a.decision === "approved" ? "Approved" : "Rejected"} by ${actorLabel(a.actor)}${a.status === "invalidated" ? `, invalidated: ${a.invalidated_reason}` : ""}${a.reason ? `: ${a.reason}` : ""}`, tone: a.status === "invalidated" ? ("warn" as const) : ("ok" as const) })),
    ...d.executions.map((e) => ({ at: e.created_at, text: `Execution ${e.status} via ${e.adapter} adapter after ${e.attempts} attempt(s)${e.last_error ? `: ${e.last_error}` : ""}`,
      detail: `key ${e.idempotency_key}`, tone: e.status === "failed" ? ("danger" as const) : ("neutral" as const),
      link: e.external_url ? { href: e.external_url, label: `GitHub issue #${e.external_number}` } : undefined })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const dot = { neutral: "bg-line-strong", warn: "bg-[#d48a1c]", ok: "bg-ok", danger: "bg-danger" };

  return (
    <aside className="pane-scroll h-full min-h-0 overflow-y-auto bg-canvas" data-testid="evidence-pane" aria-label="Request details">
      <Section title="Customer" icon={UserRound} testId="facts"
        help={<HelpTip label="Where account facts come from" align="end">Facts come from the account tools (customer lookup, subscription, existing tickets) for the authorized customer, not from the model.</HelpTip>}>
        {c ? <CustomerFacts facts={c.account_facts} category={d.category ?? c.category} />
          : <p className="pb-1 text-ui text-fg-subtle">Facts appear after the workflow looks up the authorized customer.</p>}
      </Section>

      <Section title="Sources" icon={BookOpenText} count={c?.citations.length ?? 0}
        help={<HelpTip label="About sources" align="end">Passages from this workspace's documentation that the draft cites. Select one to read it in context. Superseded versions stay readable.</HelpTip>}>
        {c && c.citations.length > 0 ? (
          <ol className="space-y-0.5 pb-1">
            {c.citations.map((ct, i) => {
              const note = versionNote(d.proposal?.citation_versions?.[ct.document_version_id], ct.version);
              return (
                <li key={ct.chunk_id}>
                  <button onClick={() => onCite(ct.chunk_id)} data-testid="citation" title={ct.claim}
                    className="grid w-full grid-cols-[1.25rem_minmax(0,1fr)] gap-x-2 rounded-md px-1.5 py-1.5 text-left transition-colors hover:bg-surface hover:shadow-xs">
                    <span className="mt-px grid size-5 place-items-center rounded bg-accent-soft text-2xs font-semibold tabular-nums text-accent-strong">{i + 1}</span>
                    <span className="min-w-0">
                      <span className="block text-ui font-medium leading-snug text-fg [overflow-wrap:anywhere]">{ct.section}</span>
                      <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-fg-subtle">
                        <FileText aria-hidden className="size-3 shrink-0" strokeWidth={1.75} />
                        <span className="truncate">{ct.doc_title}</span>
                        <span className="shrink-0 tabular-nums">v{ct.version}</span>
                      </span>
                      {note && <span className="mt-0.5 block text-xs font-medium text-warn" data-testid="citation-superseded">{note.replace(/^ · v\d+, /, "")}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        ) : <p className="pb-1 text-ui text-fg-subtle">No citations yet.</p>}
      </Section>

      <Section title="Tickets" icon={Ticket} count={d.tickets.length}>
        {d.tickets.length ? (
          <div className="space-y-2 pb-1">
            {d.tickets.map((t) => (
              <div key={t.id} className="rounded-md bg-surface px-3 py-2.5 text-ui shadow-xs ring-1 ring-line" data-testid="ticket">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-fg">{t.number}</span>
                  <span className="text-xs font-medium text-accent-strong">{humanize(t.status)}</span>
                </div>
                <p className="mt-1 text-fg [overflow-wrap:anywhere]">{t.subject}</p>
                <p className="mt-0.5 text-xs text-fg-subtle">{t.group} · {humanize(t.priority)} priority · via {t.adapter} adapter{t.sandbox ? " · Demo sandbox" : ""}</p>
                {t.external_url && (
                  <a href={t.external_url} target="_blank" rel="noopener noreferrer" data-testid="ticket-external-link"
                    className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-accent-strong underline underline-offset-2 hover:text-accent">
                    GitHub issue #{t.external_number}<ExternalLink aria-hidden className="size-3" /><span className="sr-only"> (opens in a new tab)</span>
                  </a>
                )}
              </div>
            ))}
          </div>
        ) : <p className="pb-1 text-ui text-fg-subtle">No ticket has been created or changed for this request.</p>}
      </Section>

      <Section title="Review history" icon={History} count={history.length} defaultOpen={false} testId="history-section">
        {history.length ? (
          <ol className="space-y-2 pb-1 text-ui" data-testid="history">
            {history.map((h, i) => (
              <li key={i} className="grid grid-cols-[0.5rem_minmax(0,1fr)] gap-x-2.5">
                <span aria-hidden className={`mt-1.5 size-1.5 rounded-full ${dot[h.tone]}`} />
                <div className="min-w-0">
                  <p className={`[overflow-wrap:anywhere] ${h.tone === "danger" ? "text-danger" : h.tone === "warn" ? "text-warn" : "text-fg"}`}>
                    {h.text}{h.link && <> · <a href={h.link.href} target="_blank" rel="noopener noreferrer" className="font-medium text-accent-strong underline underline-offset-2">{h.link.label}</a></>}
                  </p>
                  <p className="text-xs text-fg-subtle">{timeAgo(h.at)}{h.detail && <> · <span className="font-mono text-2xs [overflow-wrap:anywhere]">{h.detail}</span></>}</p>
                </div>
              </li>
            ))}
          </ol>
        ) : <p className="pb-1 text-ui text-fg-subtle">No review actions yet.</p>}
      </Section>
    </aside>
  );
}
