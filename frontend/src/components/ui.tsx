import type { ButtonHTMLAttributes, ReactNode } from "react";

const STATE_STYLE: Record<string, string> = {
  awaiting_review: "bg-amber-50 text-amber-800 ring-amber-200",
  approved: "bg-teal-50 text-teal-800 ring-teal-200",
  executing: "bg-teal-50 text-teal-800 ring-teal-200",
  completed: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  failed: "bg-red-50 text-red-800 ring-red-200",
  error: "bg-red-50 text-red-800 ring-red-200",
  stale: "bg-orange-50 text-orange-800 ring-orange-200",
  rejected: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  unsupported: "bg-zinc-100 text-zinc-700 ring-zinc-200",
};

export const STATE_LABEL: Record<string, string> = {
  received: "Received", classified: "Classified", context_resolved: "Context resolved", retrieved: "Retrieved",
  awaiting_review: "Awaiting review", approved: "Approved", executing: "Executing", completed: "Completed",
  failed: "Execution failed", error: "Error", stale: "Stale evidence", rejected: "Rejected", unsupported: "Unsupported",
};

export function StateBadge({ state, template }: { state: string; template?: boolean }) {
  if (template) {
    return <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset bg-white text-zinc-600 ring-zinc-300">Seeded, not run</span>;
  }
  const style = STATE_STYLE[state] ?? "bg-zinc-50 text-zinc-700 ring-zinc-200";
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}>{STATE_LABEL[state] ?? state}</span>;
}

export function Tag({ children, tone = "zinc" }: { children: ReactNode; tone?: "zinc" | "teal" | "amber" | "red" }) {
  const tones = {
    zinc: "bg-zinc-100 text-zinc-700",
    teal: "bg-teal-50 text-teal-800",
    amber: "bg-amber-50 text-amber-800",
    red: "bg-red-50 text-red-800",
  };
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" };

export function Button({ variant = "secondary", className = "", ...rest }: BtnProps) {
  const v = {
    primary: "bg-teal-700 text-white hover:bg-teal-800 disabled:bg-teal-700/40",
    secondary: "bg-white text-zinc-800 ring-1 ring-inset ring-zinc-300 hover:bg-zinc-50 disabled:text-zinc-400",
    danger: "bg-white text-red-700 ring-1 ring-inset ring-red-200 hover:bg-red-50 disabled:text-red-300",
    ghost: "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 disabled:text-zinc-300",
  }[variant];
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors active:translate-y-px disabled:cursor-not-allowed ${v} ${className}`}
    />
  );
}

export function PanelHeading({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 pb-2">
      <h3 className="text-xs font-semibold text-zinc-500">{children}</h3>
      {aside}
    </div>
  );
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
