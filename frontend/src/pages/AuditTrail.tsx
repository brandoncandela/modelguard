import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Badge, ErrorBox, Field, Panel, Spinner, useDebounced } from "../components/ui";
import { dateTime, num } from "../lib/format";

export default function AuditTrail() {
  const [f, setF] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const q = useDebounced(text);
  const list = useQuery({ queryKey: ["audit", f, q, page], queryFn: () => api("/audit/events", { query: { ...f, q, page, page_size: 50 } }) });
  const verify = useMutation({ mutationFn: () => api("/audit/verify") });
  const set = (k: string, v: string) => { setF((s) => ({ ...s, [k]: v })); setPage(1); };
  const d = list.data;
  return (
    <div className="space-y-4">
      <Panel bodyClass="flex flex-wrap items-end gap-2 p-3">
        <div className="min-w-[200px] flex-1"><Field label="Search summaries"><input className="input" value={text} onChange={(e) => { setText(e.target.value); setPage(1); }} /></Field></div>
        <div className="w-44"><Field label="Entity type"><select className="input" value={f.entity_type ?? ""} onChange={(e) => set("entity_type", e.target.value)}>
          <option value="">All</option>{(d?.entity_types ?? []).map((x: string) => <option key={x}>{x}</option>)}</select></Field></div>
        <div className="w-56"><Field label="Action"><select className="input" value={f.action ?? ""} onChange={(e) => set("action", e.target.value)}>
          <option value="">All</option>{(d?.actions ?? []).map((x: string) => <option key={x}>{x}</option>)}</select></Field></div>
        <div className="w-36"><Field label="Actor"><input className="input" value={f.actor ?? ""} onChange={(e) => set("actor", e.target.value)} /></Field></div>
        <div className="w-36"><Field label="From"><input className="input" type="date" value={f.date_from ?? ""} onChange={(e) => set("date_from", e.target.value)} /></Field></div>
        <div className="w-36"><Field label="To"><input className="input" type="date" value={f.date_to ?? ""} onChange={(e) => set("date_to", e.target.value)} /></Field></div>
        <button className="btn-primary" onClick={() => verify.mutate()} disabled={verify.isPending}>Verify hash chain</button>
      </Panel>
      {verify.data && (
        <div className={`rounded-md border px-3 py-2 text-[12.5px] ${verify.data.valid ? "border-ok/30 bg-ok/5 text-ok" : "border-bad/30 bg-bad/5 text-bad"}`} role="status">
          {verify.data.valid ? `Chain intact: ${num(verify.data.events_checked)} events verified. Head hash ${verify.data.head_hash.slice(0, 16)}…`
            : `Chain broken at ${verify.data.breaks.length} event(s): ${verify.data.breaks.map((b: any) => b.id).join(", ")}`}
        </div>)}
      <ErrorBox error={verify.error} />
      <Panel title={d ? `${num(d.total)} events` : "Events"} bodyClass="" actions={<span className="text-[11.5px] text-muted">Append-only. Updates and deletes are blocked by database triggers.</span>}>
        {list.isLoading ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-0">
              <thead><tr>{["#", "When", "Actor", "Action", "Entity", "Summary", "Hash"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
              <tbody>{d.items.map((e: any) => (<>
                <tr key={e.id} className="tr-click" onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <td className="td text-muted">{e.id}</td><td className="td whitespace-nowrap">{dateTime(e.occurred_at)}</td>
                  <td className="td"><div>{e.actor}</div><div className="text-[11px] text-muted">{e.role}</div></td>
                  <td className="td"><Badge tone={e.action.includes("FAIL") || e.action.includes("LOCK") ? "red" : e.action.includes("APPROV") || e.action.includes("DECISION") ? "green" : "neutral"}>{e.action}</Badge></td>
                  <td className="td whitespace-nowrap">{e.entity_type} <span className="text-muted">{e.entity_ref}</span></td>
                  <td className="td">{e.summary}</td><td className="td"><code className="text-[11px]" title={e.hash}>{e.hash.slice(0, 10)}…</code></td>
                </tr>
                {open === e.id && (
                  <tr key={`${e.id}-d`}><td colSpan={7} className="td bg-sunken">
                    <div className="grid gap-2 text-[12px] lg:grid-cols-2">
                      <div><div className="kv-k">Changes</div><pre className="max-h-60 overflow-auto whitespace-pre-wrap text-[11.5px]">{JSON.stringify(e.changes, null, 2)}</pre></div>
                      <div className="space-y-1 break-all"><div><span className="kv-k">Event ID</span> {e.event_id}</div><div><span className="kv-k">Request ID</span> {e.request_id ?? "–"}</div>
                        <div><span className="kv-k">Previous hash</span> <code>{e.prev_hash}</code></div><div><span className="kv-k">Hash</span> <code>{e.hash}</code></div></div>
                    </div></td></tr>)}
              </>))}</tbody>
            </table>
          </div>)}
        {d && (
          <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-2 text-[12px]">
            <span className="text-muted">Page {d.page} of {Math.max(1, Math.ceil(d.total / d.page_size))}</span>
            <button className="btn-ghost h-7" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="btn-ghost h-7" disabled={page * d.page_size >= d.total} onClick={() => setPage(page + 1)}>Next</button>
          </div>)}
      </Panel>
    </div>
  );
}
