import { useEffect, useState, type ReactNode } from "react";
import { errorText } from "../../api/client";

type Tone = "neutral" | "blue" | "green" | "amber" | "orange" | "red" | "slate";
const TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-ink border-line",
  blue: "bg-accent-soft text-accent border-accent/20",
  green: "bg-ok/10 text-ok border-ok/20",
  amber: "bg-warn/10 text-warn border-warn/25",
  orange: "bg-high/10 text-high border-high/25",
  red: "bg-bad/10 text-bad border-bad/25",
  slate: "bg-sunken text-muted border-line",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-px text-[11px] font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

const SEV: Record<string, Tone> = { Critical: "red", High: "orange", Medium: "amber", Low: "slate" };
export const SeverityBadge = ({ s }: { s?: string | null }) =>
  s ? <Badge tone={SEV[s] ?? "neutral"}><Dot tone={SEV[s] ?? "neutral"} />{s}</Badge> : <span className="text-muted">–</span>;

const STATUS: Record<string, Tone> = {
  // monitoring
  Breach: "red", Warning: "amber", "Within limits": "green", "Not monitored": "slate", "Not available": "slate",
  // approvals / validations
  Approved: "green", "Conditionally Approved": "amber", "Approved with Conditions": "amber", Rejected: "red",
  "Not Approved": "red", "Approval Expired": "red", "Pending Approval": "blue", "Pending Review": "blue",
  "In Progress": "blue", Scheduled: "slate", "Not Started": "slate", "Under Review": "blue", Draft: "slate",
  Submitted: "blue", Returned: "amber", Retired: "slate",
  // findings
  Open: "red", "Response Submitted": "amber", "In Remediation": "blue", "Pending Validation": "blue",
  Closed: "green", "Risk Accepted": "slate", Acknowledged: "amber", Resolved: "green",
  // docs, controls, tests
  Complete: "green", Partial: "amber", Incomplete: "red", Outdated: "red", Implemented: "green",
  "Partially implemented": "amber", "Not implemented": "red", Planned: "slate", Pass: "green", Fail: "red",
  Passed: "green", "Review required": "red", "Not tested": "slate", Covered: "green", "Partially covered": "amber",
  Gap: "red", "No control mapped": "red", "Historical reference": "slate", Current: "green", "In force": "green",
  Superseded: "slate", Rescinded: "slate",
  // lifecycle
  Production: "green", Development: "slate", "Pre-Implementation Validation": "blue", "Under Remediation": "amber",
  Pilot: "blue", Blocked: "red",
};
export const StatusBadge = ({ s }: { s?: string | null }) =>
  s ? <Badge tone={STATUS[s] ?? "neutral"}>{s}</Badge> : <span className="text-muted">–</span>;

export function Dot({ tone = "neutral" }: { tone?: Tone }) {
  const c = { neutral: "bg-muted", blue: "bg-accent", green: "bg-ok", amber: "bg-warn", orange: "bg-high", red: "bg-bad", slate: "bg-muted/50" }[tone];
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${c}`} />;
}

export function RiskBadge({ r }: { r: string }) {
  return <Badge tone={r === "High" ? "red" : r === "Medium" ? "amber" : "slate"}>{r}</Badge>;
}

export function Panel({ title, actions, children, className = "", bodyClass = "p-4" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-h">
          <h2 className="panel-t">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, note, tone, onClick }:
  { label: string; value: ReactNode; note?: ReactNode; tone?: "bad" | "warn" | "ok"; onClick?: () => void }) {
  const t = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <button type="button" onClick={onClick} disabled={!onClick}
      className="panel px-3.5 py-3 text-left disabled:cursor-default enabled:hover:border-accent/40">
      <div className="text-xxs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-[22px] font-semibold leading-7 ${t}`}>{value}</div>
      {note && <div className="mt-0.5 text-[11.5px] text-muted">{note}</div>}
    </button>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: ReactNode }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto shadow-[inset_0_-1px_0_rgb(var(--line))]">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-[12.5px] font-medium ${value === t.id ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-muted" role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full motion-reduce:animate-none border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div role="alert" className="rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-[12.5px] text-bad">{errorText(error)}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-8 text-center text-[12.5px] text-muted">{children}</div>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  );
}

export function Drawer({ open, onClose, title, children, width = "max-w-3xl" }:
  { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-ink/25" onClick={onClose} />
      <aside role="dialog" aria-modal="true" className={`relative flex h-full w-full ${width} flex-col bg-surface shadow-xl`}>
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-3">
          <div className="min-w-0 flex-1">{title}</div>
          <button className="btn-ghost h-7 px-2" onClick={onClose} aria-label="Close">Close</button>
        </header>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </aside>
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer }:
  { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <div role="dialog" aria-modal="true" className="relative w-full max-w-lg rounded-lg bg-surface shadow-xl">
        <div className="border-b border-line px-5 py-3 text-[14px] font-semibold">{title}</div>
        <div className="max-h-[70vh] space-y-3 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

/** Button that asks for a comment (optionally required) before running an action. */
export function ActionButton({ label, tone = "ghost", title, commentLabel, minComment = 0, extra, onRun }: {
  label: string; tone?: "primary" | "ghost" | "danger"; title?: string; commentLabel?: string; minComment?: number;
  extra?: (set: (k: string, v: string) => void, vals: Record<string, string>) => ReactNode;
  onRun: (comment: string, vals: Record<string, string>) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [vals, setVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const cls = tone === "primary" ? "btn-primary" : tone === "danger" ? "btn-danger" : "btn-ghost";
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      await onRun(comment, vals);
      setOpen(false);
      setComment("");
      setVals({});
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button className={cls} onClick={() => setOpen(true)}>{label}</button>
      <Modal open={open} onClose={() => setOpen(false)} title={title ?? label}
        footer={<><button className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
          <button className={tone === "danger" ? "btn-danger" : "btn-primary"} disabled={busy || comment.trim().length < minComment} onClick={run}>
            {busy ? "Working" : "Confirm"}</button></>}>
        {extra?.((k, v) => setVals((s) => ({ ...s, [k]: v })), vals)}
        {commentLabel !== undefined && (
          <Field label={commentLabel || "Comment"} hint={minComment ? `At least ${minComment} characters` : undefined}>
            <textarea className="textarea" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
        )}
        <ErrorBox error={err} />
      </Modal>
    </>
  );
}

export function KV({ items, cols = 3 }: { items: [string, ReactNode][]; cols?: number }) {
  return (
    <dl className={`grid gap-x-6 gap-y-3 ${cols === 2 ? "sm:grid-cols-2" : cols === 4 ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="kv-k">{k}</dt>
          <dd className="kv-v mt-0.5 break-words">{v ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Timeline({ items }: { items: { when: string; who?: string; title: ReactNode; body?: ReactNode }[] }) {
  if (!items.length) return <Empty>No history yet.</Empty>;
  return (
    <ol className="relative ml-2 border-l border-line">
      {items.map((it, i) => (
        <li key={i} className="mb-3 ml-4">
          <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-accent" />
          <div className="text-[12.5px] font-medium">{it.title}</div>
          <div className="text-[11.5px] text-muted">{it.when}{it.who ? ` · ${it.who}` : ""}</div>
          {it.body && <div className="mt-1 text-[12.5px] text-ink/90">{it.body}</div>}
        </li>
      ))}
    </ol>
  );
}

export function Stepper({ steps, current, terminal }: { steps: string[]; current: string; terminal?: string }) {
  const idx = steps.indexOf(current);
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11.5px]">
      {steps.map((s, i) => {
        const done = idx >= 0 && i < idx;
        const on = s === current;
        return (
          <li key={s} className="flex items-center gap-1">
            <span className={`rounded-full border px-2 py-0.5 ${on ? "border-accent bg-accent text-white" : done ? "border-accent/30 bg-accent-soft text-accent" : "border-line text-muted"}`}>{s}</span>
            {i < steps.length - 1 && <span className="text-line">›</span>}
          </li>
        );
      })}
      {terminal && idx < 0 && <li><StatusBadge s={terminal} /></li>}
    </ol>
  );
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-line bg-sunken px-3 py-2 text-[12px] text-muted">{children}</div>;
}
