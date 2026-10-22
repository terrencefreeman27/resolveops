import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, type AiStatus } from "../api";
import { Button, Tag } from "./ui";

const n = (v: number) => v.toLocaleString("en-US");

const LIMIT_LABELS: [string, string, (v: number) => string][] = [
  ["max_request_chars", "Request text", (v) => `${n(v)} characters max`],
  ["max_output_tokens_per_call", "Output per model call", (v) => `${n(v)} tokens max`],
  ["max_tool_steps", "Tool-calling steps", (v) => `${v} per request`],
  ["max_tokens_per_request", "Tokens per request", (v) => `${n(v)} max (input + output)`],
  ["call_timeout_s", "Per-call timeout", (v) => `${v}s`],
  ["max_retries", "Retries", (v) => `${v} (429, 5xx, overloaded, timeouts)`],
  ["rate_per_reviewer_per_min", "Rate, per reviewer", (v) => `${v} per minute`],
  ["rate_global_per_min", "Rate, all reviewers", (v) => `${v} per minute`],
  ["max_concurrency", "Concurrent live requests", (v) => `${v} (single API instance)`],
];

function Row({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-1.5" data-testid={testId}>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="text-right font-medium text-zinc-900">{children}</dd>
    </div>
  );
}

export function AiStatusDialog({ ws, onClose }: { ws: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [s, setS] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  useEffect(() => { api.aiStatus(ws).then(setS).catch((e: Error) => setError(e.message)); }, [ws]);

  const b = s?.budget;
  const pct = b && b.monthly_token_budget > 0 ? Math.min(100, (b.tokens_used / b.monthly_token_budget) * 100) : 0;

  return (
    <dialog ref={ref} onClose={onClose} data-testid="ai-status"
      className="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-xl p-0 shadow-xl backdrop:bg-zinc-900/40">
      <div className="max-h-[85dvh] space-y-5 overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">AI provider status</h2>
            <p className="mt-1 text-sm text-zinc-600">Server configuration for this workspace. Credentials stay on the server; only whether a key is present is shown.</p>
          </div>
          <Button variant="ghost" onClick={() => ref.current?.close()} aria-label="Close AI status">Close</Button>
        </div>
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        {!s && !error && <p className="text-sm text-zinc-500">Loading</p>}
        {s && b && (
          <>
            <dl className="divide-y divide-zinc-100 text-sm">
              <Row label="Mode" testId="ai-status-mode">{s.mode === "live" ? <Tag tone="teal">Live</Tag> : <Tag tone="amber">Demo (simulated)</Tag>}</Row>
              <Row label="Model">{s.model} <span className="font-normal text-zinc-500">· effort {s.effort}</span></Row>
              <Row label="API key configured" testId="ai-status-key">
                {s.key_configured ? <Tag tone="teal">Yes</Tag> : <Tag tone={s.mode === "live" ? "red" : "zinc"}>No</Tag>}
              </Row>
              <Row label="Refusal fallback">{s.refusal_fallback ? "Server-side default" : "Off"}</Row>
              <Row label="Live for public visitors">{s.live_for_visitors ? "Enabled" : "Disabled (reviewers only)"}</Row>
            </dl>
            {s.mode === "live" && !s.key_configured && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="status">
                ANTHROPIC_API_KEY is not configured. Live requests go to an error state with this message; no simulated output is substituted.
              </p>
            )}

            <section>
              <h3 className="text-xs font-semibold text-zinc-500">Live budget this month</h3>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-100" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Token budget used">
                <div className={`h-full ${pct >= 90 ? "bg-red-600" : "bg-teal-700"}`} style={{ width: `${pct}%` }} />
              </div>
              <dl className="mt-1 divide-y divide-zinc-100 text-sm">
                <Row label="Tokens used" testId="ai-status-budget">{n(b.tokens_used)} of {n(b.monthly_token_budget)}</Row>
                <Row label="Tokens remaining">{n(b.tokens_remaining)}</Row>
                <Row label="Cost">{b.pricing ? `$${(b.cost_usd ?? 0).toFixed(2)}${b.monthly_usd_budget != null ? ` of $${b.monthly_usd_budget.toFixed(2)}` : ""}` : "Not estimated (no pricing configured)"}</Row>
                {b.pricing && <Row label="Pricing assumption">${b.pricing.input_per_mtok_usd} / ${b.pricing.output_per_mtok_usd} per million input / output tokens</Row>}
              </dl>
            </section>

            <section>
              <h3 className="text-xs font-semibold text-zinc-500">Runs this month</h3>
              <dl className="mt-1 divide-y divide-zinc-100 text-sm">
                <Row label="Live (Claude)">{s.usage_this_month.live.runs} runs · {s.usage_this_month.live.errors} errors</Row>
                <Row label="Simulated">{s.usage_this_month.simulated.runs} runs · no model tokens</Row>
              </dl>
            </section>

            <section>
              <h3 className="text-xs font-semibold text-zinc-500">Limits</h3>
              <dl className="mt-1 divide-y divide-zinc-100 text-sm">
                {LIMIT_LABELS.filter(([k]) => k in s.limits).map(([k, label, fmt]) => <Row key={k} label={label}>{fmt(s.limits[k])}</Row>)}
              </dl>
            </section>
          </>
        )}
      </div>
    </dialog>
  );
}
