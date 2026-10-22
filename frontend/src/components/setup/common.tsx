import type { ReactNode } from "react";

export const field = "w-full rounded-md border-0 bg-white px-2.5 py-1.5 text-sm text-zinc-900 ring-1 ring-inset ring-zinc-300 focus:ring-2 focus:ring-teal-600";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-sm font-medium text-zinc-700">
      {label}
      {children}
      {hint && <span className="text-xs font-normal text-zinc-500">{hint}</span>}
    </label>
  );
}

export function StepHeader({ n, title, children }: { n: number; title: string; children?: ReactNode }) {
  return (
    <header className="mb-5">
      <p className="text-xs font-semibold text-teal-700">Step {n} of 6</p>
      <h2 className="mt-0.5 text-lg font-semibold tracking-tight text-zinc-900">{title}</h2>
      {children && <p className="mt-1 max-w-2xl text-sm text-zinc-600">{children}</p>}
    </header>
  );
}

export function Alert({ tone, children, testId }: { tone: "error" | "ok" | "info"; children: ReactNode; testId?: string }) {
  const cls = { error: "bg-red-50 text-red-800", ok: "bg-teal-50 text-teal-900", info: "bg-zinc-100 text-zinc-700" }[tone];
  return <div role={tone === "error" ? "alert" : "status"} data-testid={testId} className={`rounded-md px-3 py-2 text-sm ${cls}`}>{children}</div>;
}

export const IMPORT_STYLE: Record<string, string> = {
  pending: "bg-zinc-100 text-zinc-700", processing: "bg-amber-50 text-amber-800",
  ready: "bg-emerald-50 text-emerald-800", failed: "bg-red-50 text-red-800",
};

export function Pill({ className, children, testId }: { className: string; children: ReactNode; testId?: string }) {
  return <span data-testid={testId} className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}
