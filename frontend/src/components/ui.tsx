import { type ButtonHTMLAttributes, type ReactNode, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { ChevronRight, CircleHelp, LoaderCircle, type LucideIcon } from "lucide-react";
import { STATE_LABEL, type RequestStatus, type Tone } from "../labels";

export { STATE_LABEL };

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-fg-muted", accent: "text-accent-strong", warn: "text-warn", danger: "text-danger", ok: "text-ok",
};
const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-fg-subtle/60", accent: "bg-accent", warn: "bg-[#d48a1c]", danger: "bg-danger", ok: "bg-ok",
};
const TONE_CHIP: Record<Tone, string> = {
  neutral: "bg-sunken text-fg-muted", accent: "bg-accent-soft text-accent-strong", warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger", ok: "bg-ok-soft text-ok",
};

/** A status as a coloured dot plus a word: the one status signal in rows and headers. */
export function StatusLabel({ status, className = "" }: { status: RequestStatus; className?: string }) {
  const ready = status.key === "ready";
  return (
    <span className={`inline-flex min-w-0 items-center gap-1.5 text-xs font-medium ${TONE_TEXT[status.tone]} ${className}`} data-status={status.key}>
      <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${ready ? "bg-transparent ring-1 ring-fg-subtle" : TONE_DOT[status.tone]}`} />
      <span className="truncate">{status.label}</span>
    </span>
  );
}

/** Status as a soft chip, used once per request header; the detail ("Awaiting review") follows quietly. */
export function StateBadge({ status }: { status: RequestStatus }) {
  const ready = status.key === "ready";
  return (
    <span className="inline-flex shrink-0 items-center gap-2" data-testid="state-badge" data-status={status.key}>
      <span className={`inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-xs font-medium ${TONE_CHIP[status.tone]}`}>
        <span aria-hidden className={`size-1.5 rounded-full ${ready ? "bg-transparent ring-1 ring-fg-subtle" : TONE_DOT[status.tone]}`} />
        {status.label}
      </span>
      {status.detail && <span className="text-xs text-fg-subtle">{status.detail}</span>}
    </span>
  );
}

const LEGACY_TONE: Record<string, Tone> = { zinc: "neutral", teal: "accent", amber: "warn", red: "danger" };
export function Tag({ children, tone = "zinc" }: { children: ReactNode; tone?: "zinc" | "teal" | "amber" | "red" | Tone }) {
  const t = (LEGACY_TONE[tone] ?? tone) as Tone;
  return <span className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium ${TONE_CHIP[t]}`}>{children}</span>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  icon?: LucideIcon;
  loading?: boolean;
};

export function Button({ variant = "secondary", size = "md", icon: Icon, loading, className = "", children, disabled, ...rest }: BtnProps) {
  const v = {
    primary: "bg-accent text-white shadow-xs hover:bg-accent-strong disabled:bg-accent/45 disabled:shadow-none",
    secondary: "bg-surface text-fg ring-1 ring-inset ring-line-strong shadow-xs hover:bg-canvas disabled:text-fg-subtle/70 disabled:bg-surface disabled:ring-line disabled:shadow-none",
    danger: "bg-surface text-danger ring-1 ring-inset ring-danger-line hover:bg-danger-soft disabled:text-danger/45",
    ghost: "text-fg-muted hover:bg-sunken hover:text-fg disabled:text-fg-subtle/60 disabled:bg-transparent",
  }[variant];
  const s = size === "sm" ? "h-7 px-2.5" : "h-8 px-3";
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-ui font-medium transition-[background-color,color,box-shadow] duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:active:translate-y-0 ${s} ${v} ${className}`}
    >
      {loading ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : Icon ? <Icon aria-hidden className="size-4" strokeWidth={1.75} /> : null}
      {children}
    </button>
  );
}

/** Square icon-only button. `label` is required and becomes the accessible name and tooltip. */
export function IconButton({ icon: Icon, label, className = "", tone = "light", ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { icon: LucideIcon; label: string; tone?: "light" | "rail" }) {
  const t = tone === "rail"
    ? "text-rail-fg hover:bg-white/[0.06] hover:text-white aria-[current=page]:bg-white/[0.14] aria-[current=page]:text-white aria-expanded:bg-white/10 aria-expanded:text-white"
    : "text-fg-muted hover:bg-sunken hover:text-fg aria-expanded:bg-sunken aria-expanded:text-fg";
  return (
    <button type="button" aria-label={label} title={label} {...rest}
      className={`inline-flex size-8 shrink-0 items-center justify-center rounded-md transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40 ${t} ${className}`}>
      <Icon aria-hidden className={tone === "rail" ? "size-[18px]" : "size-4"} strokeWidth={1.75} />
    </button>
  );
}

export function PanelHeading({ children, aside, id }: { children: ReactNode; aside?: ReactNode; id?: string }) {
  return (
    <div className="flex min-h-6 items-center justify-between gap-2 pb-1.5">
      <h3 id={id} className="text-xs font-semibold text-fg-muted">{children}</h3>
      {aside}
    </div>
  );
}

/** Collapsible section with a quiet header; used for progressive disclosure in the panes. */
export function Disclosure({ title, meta, defaultOpen = false, children, testId, className = "", icon: Icon }: {
  title: ReactNode; meta?: ReactNode; defaultOpen?: boolean; children: ReactNode; testId?: string; className?: string; icon?: LucideIcon;
}) {
  // Own open state for the chevron: a CSS group selector would also match an open *ancestor* disclosure.
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details open={defaultOpen} className={className} data-testid={testId} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex cursor-pointer select-none items-center gap-2 rounded-md py-1.5 text-ui font-medium text-fg transition-colors hover:text-accent-strong">
        <ChevronRight aria-hidden className={`size-4 shrink-0 text-fg-subtle transition-transform duration-150 ${open ? "rotate-90" : ""}`} strokeWidth={1.75} />
        {Icon && <Icon aria-hidden className="size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} />}
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {meta && <span className="shrink-0 text-xs font-normal text-fg-subtle">{meta}</span>}
      </summary>
      <div className="pt-1">{children}</div>
    </details>
  );
}

/**
 * Floating panel anchored to a trigger. Rendered position:fixed so pane overflow never clips it.
 * Closes on Escape (focus returns to the trigger) and on outside click.
 */
export function Popover({ trigger, children, align = "start", width = 320, label, testId }: {
  trigger: (p: { ref: (el: HTMLButtonElement | null) => void; open: boolean; toggle: () => void; id: string }) => ReactNode;
  children: (close: () => void) => ReactNode; align?: "start" | "end"; width?: number; label: string; testId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; w: number } | null>(null);
  const btn = useRef<HTMLButtonElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const id = useId();
  const close = useCallback(() => { setOpen(false); btn.current?.focus(); }, []);
  const place = useCallback(() => {
    const r = btn.current?.getBoundingClientRect(); if (!r) return;
    const w = Math.min(width, window.innerWidth - 16);
    let left = align === "end" ? r.right - w : r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    const h = panel.current?.offsetHeight ?? 240;
    const top = r.bottom + 6 + h > window.innerHeight - 8 && r.top - 6 - h > 8 ? r.top - 6 - h : r.bottom + 6;
    setPos({ top, left, w });
  }, [align, width]);
  useLayoutEffect(() => { if (open) place(); }, [open, place]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("resize", place);
    const raf = requestAnimationFrame(() => { place(); panel.current?.querySelector<HTMLElement>("button:not(:disabled), a[href], input, select")?.focus(); });
    return () => { cancelAnimationFrame(raf); window.removeEventListener("keydown", onKey, true); window.removeEventListener("mousedown", onDown); window.removeEventListener("resize", place); };
  }, [open, close, place]);
  return (
    <>
      {trigger({ ref: (el) => { btn.current = el; }, open, toggle: () => setOpen((o) => !o), id })}
      {open && (
        <div ref={panel} id={id} role="dialog" aria-label={label} data-testid={testId}
          style={{ position: "fixed", top: pos?.top ?? -9999, left: pos?.left ?? -9999, width: pos?.w ?? width }}
          className="anim-pop z-50 max-h-[calc(100dvh-16px)] overflow-y-auto rounded-lg bg-surface p-1 text-ui text-fg shadow-pop ring-1 ring-line">
          {children(() => setOpen(false))}
        </div>
      )}
    </>
  );
}

/** Contextual help: a small "?" that opens a short explanation. */
export function HelpTip({ label, children, align = "start", testId }: { label: string; children: ReactNode; align?: "start" | "end"; testId?: string }) {
  return (
    <Popover label={label} align={align} width={300} testId={testId}
      trigger={({ ref, open, toggle, id }) => (
        <button ref={ref} type="button" onClick={toggle} aria-expanded={open} aria-controls={open ? id : undefined} aria-label={label} title={label}
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-full text-fg-subtle transition-colors hover:bg-sunken hover:text-fg">
          <CircleHelp aria-hidden className="size-3.5" strokeWidth={1.75} />
        </button>
      )}>
      {() => <div className="space-y-1.5 px-3 py-2.5 text-ui leading-relaxed text-fg-muted">{children}</div>}
    </Popover>
  );
}

/** Menu item for Popover-based menus. */
export function MenuItem({ icon: Icon, children, hint, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { icon?: LucideIcon; hint?: ReactNode }) {
  return (
    <button type="button" {...rest}
      className="flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-canvas focus-visible:bg-canvas disabled:cursor-not-allowed disabled:opacity-50">
      {Icon && <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-subtle" strokeWidth={1.75} />}
      <span className="min-w-0 flex-1">
        <span className="block text-ui font-medium text-fg">{children}</span>
        {hint && <span className="mt-0.5 block text-xs leading-snug text-fg-subtle">{hint}</span>}
      </span>
    </button>
  );
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
