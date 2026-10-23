import type { ReactNode } from "react";

export const field = "w-full rounded-md border-0 bg-surface px-2.5 py-1.5 text-sm text-fg ring-1 ring-inset ring-line-strong hover:ring-fg-subtle/60 focus:ring-2 focus:ring-accent";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm font-medium text-fg-muted">
      {label}
      {children}
      {hint && <span className="text-xs font-normal text-fg-subtle">{hint}</span>}
    </label>
  );
}

export function StepHeader({ n, title, children }: { n: number; title: string; children?: ReactNode }) {
  return (
    <header className="mb-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold tracking-tight text-fg">{title}</h2>
        <span className="text-xs tabular-nums text-fg-subtle">Step {n} of 6</span>
      </div>
      {children && <p className="mt-1 max-w-2xl text-sm text-fg-muted">{children}</p>}
    </header>
  );
}

export function Alert({ tone, children, testId }: { tone: "error" | "ok" | "info"; children: ReactNode; testId?: string }) {
  const cls = { error: "bg-danger-soft text-danger", ok: "bg-accent-soft text-accent-strong", info: "bg-sunken text-fg-muted" }[tone];
  return <div role={tone === "error" ? "alert" : "status"} data-testid={testId} className={`rounded-md px-3 py-2 text-sm ${cls}`}>{children}</div>;
}

export const IMPORT_STYLE: Record<string, string> = {
  pending: "bg-sunken text-fg-muted", processing: "bg-warn-soft text-warn",
  ready: "bg-ok-soft text-ok", failed: "bg-danger-soft text-danger",
};

export function Pill({ className, children, testId }: { className: string; children: ReactNode; testId?: string }) {
  return <span data-testid={testId} className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}
