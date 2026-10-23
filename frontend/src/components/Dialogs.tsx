import { useEffect, useRef, useState } from "react";
import { api, type ApiError } from "../api";
import { Button } from "./ui";

const field = "w-full rounded-md border-0 bg-surface px-2.5 py-1.5 text-sm text-fg ring-1 ring-inset ring-line-strong";

function useModal(onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return { ref, close: () => ref.current?.close(), onClose };
}

export function LoginDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const m = useModal(onClose);
  const [email, setEmail] = useState("reviewer@northstar.example");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <dialog ref={m.ref} onClose={onClose} className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-xl p-0 shadow-sheet">
      <form className="space-y-4 p-5" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setError(null);
        try { await api.login(email, password); onDone(); m.close(); } catch (err) { setError((err as ApiError).message); } finally { setBusy(false); }
      }}>
        <div>
          <h2 className="text-base font-semibold">Reviewer sign-in</h2>
          <p className="mt-1 text-sm text-fg-muted">Reviewers work on the real workspace queue. Visitors can try everything in a private demo sandbox without signing in.</p>
        </div>
        <label className="grid gap-1.5 text-sm font-medium text-fg-muted">Email
          <input className={field} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-fg-muted">Password
          <input className={field} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={m.close}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy}>Sign in</Button>
        </div>
      </form>
    </dialog>
  );
}

export function NewRequestDialog({ ws, mode, onClose, onCreated }: {
  ws: string; mode: string; onClose: () => void; onCreated: (id: string) => void;
}) {
  const m = useModal(onClose);
  const [customers, setCustomers] = useState<{ id: string; company_name: string; contact_name: string; plan: string }[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.customers(ws).then((r) => { setCustomers(r.customers); setCustomerId(r.customers[0]?.id ?? ""); }).catch((e) => setError(e.message));
  }, [ws]);
  return (
    <dialog ref={m.ref} onClose={onClose} className="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-xl p-0 shadow-sheet">
      <form className="space-y-4 p-5" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setError(null);
        try {
          await api.customerSession(ws, customerId);
          const d = await api.submit(ws, subject, body);
          onCreated(d.id); m.close();
        } catch (err) { setError((err as ApiError).message); } finally { setBusy(false); }
      }}>
        <div>
          <h2 className="text-base font-semibold">Submit as a synthetic customer</h2>
          <p className="mt-1 text-sm text-fg-muted">
            The server issues a customer session for the account you pick; the message text can never switch accounts.
            {mode === "demo" && " In demo mode only the seeded scenario messages are processed. Anything else is recorded and clearly marked as not processed."}
            {mode === "live" && " Live mode: the message is sent to the live model as untrusted data, within the configured size, rate and budget limits."}
          </p>
        </div>
        <label className="grid gap-1.5 text-sm font-medium text-fg-muted">Customer (synthetic)
          <select className={field} value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.company_name}, {c.contact_name} ({c.plan})</option>)}
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-fg-muted">Subject
          <input className={field} value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} required />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-fg-muted">Message
          <textarea className={`${field} min-h-32`} value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} required />
          <span className="text-xs font-normal text-fg-subtle">{body.length} / 4000 characters</span>
        </label>
        {error && <p className="text-sm text-danger" role="alert">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={m.close}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy || !customerId}>Submit</Button>
        </div>
      </form>
    </dialog>
  );
}
