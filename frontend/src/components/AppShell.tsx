import type { ReactNode } from "react";
import {
  Building2, ChartColumn, ChevronDown, CircleAlert, CircleCheck, FlaskConical, Gauge, Inbox, LogIn, LogOut, Plus, Radio, RotateCcw,
  Search, Settings2, Sparkles, UserRound, X,
} from "lucide-react";
import type { Meta, Scenario, Workspace } from "../api";
import { Button, HelpTip, IconButton, MenuItem, Popover } from "./ui";

export type View = "inbox" | "setup" | "dashboard";

function Mark() {
  return (
    <span className="grid size-8 place-items-center rounded-md bg-accent text-white shadow-xs" aria-hidden>
      <svg viewBox="0 0 20 20" className="size-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 15V5h5.5a3 3 0 0 1 0 6H5" /><path d="m10.5 11 4.5 4" />
      </svg>
    </span>
  );
}

/** Compact dark navigation rail (vertical from md, a top strip below). */
export function Rail({ view, go, signedIn, isReviewer, meta, ws, busy, onAiStatus, onSignIn, onSignOut, onReset }: {
  view: View; go: (v: View) => void; signedIn: boolean; isReviewer: boolean; meta: Meta | null; ws: Workspace | undefined; busy: boolean;
  onAiStatus: () => void; onSignIn: () => void; onSignOut: () => void; onReset: () => void;
}) {
  const nav: { v: View; label: string; icon: typeof Inbox; testId: string; show: boolean }[] = [
    { v: "inbox", label: "Support inbox", icon: Inbox, testId: "open-inbox", show: true },
    { v: "dashboard", label: "Dashboard", icon: ChartColumn, testId: "open-dashboard", show: true },
    { v: "setup", label: "Workspace setup", icon: Settings2, testId: "open-setup", show: signedIn },
  ];
  const who = isReviewer ? `${meta?.reviewer?.name}` : signedIn ? `${meta?.reviewer?.name}` : "Visitor";
  const scope = isReviewer ? `Reviewer · ${ws?.name ?? ""}` : signedIn ? `Signed in · not a reviewer of ${ws?.name ?? "this workspace"}` : "Private demo sandbox";
  return (
    <nav aria-label="Primary" className="on-rail flex shrink-0 items-center gap-1 bg-rail px-2 py-1.5 md:w-14 md:flex-col md:px-0 md:py-3">
      <span className="mr-2 md:mb-3 md:mr-0" title="ResolveOps"><Mark /><span className="sr-only">ResolveOps</span></span>
      {nav.filter((n) => n.show).map((n) => (
        <IconButton key={n.v} tone="rail" icon={n.icon} label={n.label} data-testid={n.testId} aria-current={view === n.v ? "page" : undefined}
          onClick={() => go(n.v)} className="size-9" />
      ))}
      <span className="flex-1" />
      {isReviewer && <IconButton tone="rail" icon={Gauge} label="AI status" data-testid="ai-status-open" onClick={onAiStatus} className="size-9" />}
      <Popover label="Account" align="start" width={280} testId="account-panel"
        trigger={({ ref, open, toggle, id }) => (
          <button ref={ref} onClick={toggle} aria-expanded={open} aria-controls={open ? id : undefined} aria-label={`Account: ${who}`} title="Account"
            data-testid="account-menu"
            className="grid size-9 place-items-center rounded-md text-rail-fg transition-colors hover:bg-rail-hover hover:text-white aria-expanded:bg-rail-hover">
            <span className={`grid size-7 place-items-center rounded-full text-2xs font-semibold ${signedIn ? "bg-accent text-white" : "bg-rail-hover text-rail-fg ring-1 ring-white/15"}`}>
              {signedIn ? (meta?.reviewer?.name ?? "R").split(" ").map((s) => s[0]).join("").slice(0, 2) : <UserRound aria-hidden className="size-3.5" strokeWidth={2} />}
            </span>
          </button>
        )}>
        {(close) => (
          <div>
            <div className="border-b border-line px-2.5 pb-2.5 pt-2">
              <p className="text-ui font-semibold text-fg" data-testid="scope">{isReviewer ? `${meta?.reviewer?.name}, reviewer` : signedIn ? meta?.reviewer?.name : "Visitor, private demo sandbox"}</p>
              <p className="mt-0.5 text-xs text-fg-subtle">{signedIn ? `${meta?.reviewer?.email} · ${scope}` : "Not signed in"}</p>
              {!signedIn && <p className="mt-1.5 text-xs leading-snug text-fg-muted">Your requests and tickets are private to this browser session. Other visitors never see them.</p>}
            </div>
            <div className="pt-1">
              {!isReviewer && (
                <MenuItem icon={RotateCcw} data-testid="reset-demo" disabled={busy} hint="Deletes your session's requests and tickets."
                  onClick={() => { close(); onReset(); }}>Reset my demo</MenuItem>
              )}
              {signedIn
                ? <MenuItem icon={LogOut} onClick={() => { close(); onSignOut(); }}>Sign out</MenuItem>
                : <MenuItem icon={LogIn} hint="Reviewers work on the real workspace queue." onClick={() => { close(); onSignIn(); }}>Reviewer sign-in</MenuItem>}
            </div>
          </div>
        )}
      </Popover>
    </nav>
  );
}

/** The demo/live label: always visible, with the full explanation one click away. */
export function ModeIndicator({ meta }: { meta: Meta | null }) {
  let tone = "bg-sunken text-fg-muted";
  let icon = Radio;
  let label = "Connecting";
  let help: ReactNode = "Checking the server's AI mode.";
  if (meta?.mode === "demo") {
    tone = "bg-warn-soft text-warn"; icon = FlaskConical; label = "Demo mode · Simulated AI";
    help = <>Outputs are deterministic fixtures on synthetic data. {meta.github_issues
      ? "Approved escalations in workspaces using GitHub Issues create real issues in the configured test repository."
      : "Tickets are internal only."} Nothing changes until a reviewer approves.</>;
  } else if (meta && meta.effective_mode === "demo") {
    tone = "bg-warn-soft text-warn"; icon = FlaskConical; label = "Demo mode · Simulated AI";
    help = "The server runs live, but visitors stay on simulated AI. Live model calls are limited to signed-in reviewers.";
  } else if (meta && !meta.live_configured) {
    tone = "bg-danger-soft text-danger"; icon = CircleAlert; label = "Live mode · API key missing";
    help = "ANTHROPIC_API_KEY is not configured. Requests stop with a configuration error until the key is set on the server. Nothing is simulated.";
  } else if (meta) {
    tone = "bg-accent-soft text-accent-strong"; icon = Radio; label = `Live · ${meta.provider_label}`;
    help = "Proposals come from a real model. Nothing executes without reviewer approval.";
  }
  const Icon = icon;
  return (
    <span className="inline-flex min-w-0 items-center gap-1">
      <span className={`inline-flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ${tone}`}
        data-testid="mode-banner" data-mode={meta?.effective_mode ?? ""}>
        <Icon aria-hidden className="size-3.5 shrink-0" strokeWidth={2} />
        <span className="truncate">{label.split(" · ")[0]}<span className={meta && meta.effective_mode === "live" ? "" : "max-sm:hidden"}>{label.includes(" · ") ? ` · ${label.split(" · ").slice(1).join(" · ")}` : ""}</span></span>
      </span>
      <HelpTip label="About this mode" align="end" testId="mode-help">{help}</HelpTip>
    </span>
  );
}

export function ScenarioMenu({ scenarios, busy, onRun }: { scenarios: Scenario[]; busy: boolean; onRun: (s: Scenario) => void }) {
  if (!scenarios.length) return null;
  return (
    <Popover label="Try a scenario" align="end" width={340} testId="scenario-panel"
      trigger={({ ref, open, toggle, id }) => (
        <button ref={ref} onClick={toggle} aria-expanded={open} aria-controls={open ? id : undefined} disabled={busy} data-testid="scenario-menu"
          aria-label="Try a scenario"
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md bg-surface px-2.5 text-ui font-medium text-fg shadow-xs ring-1 ring-inset ring-line-strong transition-colors hover:bg-canvas aria-expanded:bg-canvas disabled:cursor-not-allowed disabled:text-fg-subtle/70">
          <Sparkles aria-hidden className="size-4 text-accent" strokeWidth={1.75} />
          <span className="hidden sm:inline">Try a scenario</span>
          <ChevronDown aria-hidden className="size-3.5 text-fg-subtle" strokeWidth={2} />
        </button>
      )}>
      {(close) => (
        <div>
          <p className="px-2.5 pb-1.5 pt-2 text-xs leading-snug text-fg-subtle">Each scenario runs the real workflow on synthetic data and stops at a proposal for your review.</p>
          {scenarios.map((s) => (
            <MenuItem key={s.key} data-testid={`scenario-${s.key}`} hint={s.description} disabled={busy}
              onClick={() => { close(); onRun(s); }}>{s.label}</MenuItem>
          ))}
        </div>
      )}
    </Popover>
  );
}

export function TopBar({ meta, ws, slug, onWorkspace, query, setQuery, showInboxTools, scenarios, busy, onRunScenario, onNewRequest }: {
  meta: Meta | null; ws: Workspace | undefined; slug: string; onWorkspace: (s: string) => void;
  query: string; setQuery: (q: string) => void; showInboxTools: boolean;
  scenarios: Scenario[]; busy: boolean; onRunScenario: (s: Scenario) => void; onNewRequest: () => void;
}) {
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-3 py-2 sm:px-4">
      <label className="relative order-1 flex min-w-0 items-center max-sm:flex-1 max-sm:basis-[calc(100%-9.5rem)]">
        <span className="sr-only">Workspace</span>
        <Building2 aria-hidden className="pointer-events-none absolute left-2 size-4 text-fg-subtle" strokeWidth={1.75} />
        <select data-testid="workspace-switcher" value={slug} onChange={(e) => onWorkspace(e.target.value)} title={ws?.name}
          className="h-8 w-full max-w-[20rem] truncate rounded-md sm:w-auto border-0 bg-transparent py-0 pl-8 pr-7 text-ui font-semibold text-fg ring-1 ring-inset ring-transparent transition-colors hover:bg-canvas hover:ring-line">
          {meta?.workspaces.map((w) => <option key={w.slug} value={w.slug}>{w.name}{w.profile?.fictional ? " (fictional)" : ""}</option>)}
        </select>
      </label>
      {showInboxTools && (
        <label className="relative order-3 flex min-w-0 flex-1 basis-40 items-center sm:order-2 sm:max-w-xs sm:basis-32 xl:basis-48">
          <span className="sr-only">Search requests</span>
          <Search aria-hidden className="pointer-events-none absolute left-2.5 size-4 text-fg-subtle" strokeWidth={1.75} />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search subject, customer or sender"
            className="h-8 w-full rounded-md border-0 bg-canvas pl-8 pr-8 text-ui text-fg ring-1 ring-inset ring-line placeholder:text-fg-subtle hover:ring-line-strong focus:bg-surface [&::-webkit-search-cancel-button]:hidden" />
          {query && <IconButton icon={X} label="Clear search" onClick={() => setQuery("")} className="absolute right-0.5 size-7" />}
        </label>
      )}
      <div className="order-2 flex min-w-0 items-center sm:order-3 sm:ml-auto">
        <ModeIndicator meta={meta} />
      </div>
      <div className="order-4 flex items-center gap-2">
        {showInboxTools && <ScenarioMenu scenarios={scenarios} busy={busy} onRun={onRunScenario} />}
        {showInboxTools && (
          <Button variant="primary" icon={Plus} onClick={onNewRequest} disabled={!slug} aria-label="New request" className="max-sm:w-8 max-sm:px-0">
            <span className="max-sm:hidden">New request</span>
          </Button>
        )}
      </div>
    </header>
  );
}

export type Flash = { text: string; requestId?: string; subject?: string };

/**
 * Notifications. Request-specific ones always name their request; when that request isn't the one on
 * screen, the bar says so and offers to open it. Errors stay until dismissed or resolved.
 */
export function FlashBar({ error, notice, currentId, onOpen, onDismiss }: {
  error: Flash | null; notice: Flash | null; currentId: string | null; onOpen: (id: string) => void; onDismiss: () => void;
}) {
  const f = error ?? notice;
  if (!f) return null;
  const elsewhere = !!f.requestId && f.requestId !== currentId;
  return (
    <div className={`flex shrink-0 items-center gap-2.5 border-b px-4 py-1.5 text-ui ${error ? "border-danger-line bg-danger-soft text-danger" : "border-accent-line bg-accent-soft text-accent-strong"}`}
      role={error ? "alert" : "status"} data-testid={error ? "error" : "notice"} data-request-id={f.requestId ?? ""}>
      {error ? <CircleAlert aria-hidden className="size-4 shrink-0" strokeWidth={2} /> : <CircleCheck aria-hidden className="size-4 shrink-0" strokeWidth={2} />}
      <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">
        {f.subject && <span className="font-semibold" data-testid="flash-subject">{elsewhere ? "Another request, " : ""}“{f.subject}”: </span>}
        {f.text}
      </span>
      {elsewhere && f.requestId && (
        <button type="button" onClick={() => onOpen(f.requestId!)} data-testid="flash-open"
          className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold underline underline-offset-2 hover:bg-white/60">Open request</button>
      )}
      <IconButton icon={X} label={error ? "Dismiss error" : "Dismiss notification"} onClick={onDismiss} className="size-7 text-current hover:bg-white/60 hover:text-current" />
    </div>
  );
}
