import { useState } from "react";
import type { Meta, Workspace } from "../../api";
import { Button } from "../ui";
import { AdapterStep } from "./AdapterStep";
import { CompanyStep } from "./CompanyStep";
import { DocumentsStep } from "./DocumentsStep";
import { RulesStep } from "./RulesStep";
import { TestStep } from "./TestStep";

const STEPS = ["Company details", "Import documents", "Review documents", "Escalation rules", "Ticket adapter", "Test a request"];

export function SetupView({ meta, ws, signedIn, onSignIn, onWorkspaceCreated, onMetaChanged, onOpenInbox }: {
  meta: Meta | null; ws: Workspace | null; signedIn: boolean; onSignIn: () => void;
  onWorkspaceCreated: (slug: string) => Promise<void>; onMetaChanged: () => Promise<void>; onOpenInbox: () => void;
}) {
  const [step, setStep] = useState(0);
  const member = signedIn && !!ws?.is_member;

  if (!signedIn) {
    return (
      <section className="grid flex-1 place-items-center bg-white p-10 text-center" data-testid="setup-denied">
        <div className="max-w-md">
          <h1 className="text-lg font-semibold text-zinc-900">Workspace setup is for reviewers</h1>
          <p className="mt-2 text-sm text-zinc-600">Creating workspaces, importing documents and changing escalation rules require reviewer sign-in. The server refuses these actions for demo visitors.</p>
          <div className="mt-4 flex justify-center gap-2"><Button variant="primary" onClick={onSignIn}>Reviewer sign-in</Button><Button variant="ghost" onClick={onOpenInbox}>Back to the inbox</Button></div>
        </div>
      </section>
    );
  }

  return (
    <div className="grid flex-1 grid-cols-1 bg-white md:grid-cols-[15rem_minmax(0,1fr)] xl:min-h-0" data-testid="setup">
      <nav className="border-b border-zinc-200 bg-zinc-50 p-3 md:border-b-0 md:border-r" aria-label="Setup steps">
        <p className="px-2 pb-2 text-xs font-semibold text-zinc-500">{member ? `Setting up ${ws?.name}` : "New workspace"}</p>
        <ol className="grid grid-cols-2 gap-1 sm:grid-cols-3 md:grid-cols-1">
          {STEPS.map((label, i) => (
            <li key={label}>
              <button disabled={i > 0 && !member} onClick={() => setStep(i)} data-testid={`setup-step-${i + 1}`} aria-current={step === i}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:text-zinc-400 ${step === i ? "bg-white font-medium text-zinc-900 ring-1 ring-teal-600" : "text-zinc-700 hover:bg-white"}`}>
                <span className={`grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${step === i ? "bg-teal-700 text-white" : "bg-zinc-200 text-zinc-600"}`}>{i + 1}</span>
                {label}
              </button>
            </li>
          ))}
        </ol>
        {meta && !member && <p className="mt-3 px-2 text-xs text-zinc-500">You are not a reviewer of {ws?.name}. Create a workspace, or switch to one you belong to.</p>}
      </nav>
      <div className="min-h-0 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-4xl">
          {step === 0 && <CompanyStep ws={member ? ws : null} onCreated={async (slug) => { await onWorkspaceCreated(slug); setStep(1); }} onSaved={onMetaChanged} />}
          {member && ws && step === 1 && <DocumentsStep ws={ws.slug} mode="import" onNext={() => setStep(2)} />}
          {member && ws && step === 2 && <DocumentsStep ws={ws.slug} mode="review" onNext={() => setStep(3)} />}
          {member && ws && step === 3 && <RulesStep ws={ws.slug} onNext={() => setStep(4)} />}
          {member && ws && step === 4 && <AdapterStep ws={ws.slug} onNext={() => setStep(5)} />}
          {member && ws && step === 5 && <TestStep ws={ws.slug} />}
        </div>
      </div>
    </div>
  );
}
