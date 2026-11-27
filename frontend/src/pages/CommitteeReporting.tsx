import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { Badge, ErrorBox, Notice, Panel, SeverityBadge, Spinner, StatusBadge, Tabs } from "../components/ui";
import { date, dateTime, dec, num, pct } from "../lib/format";

const COMMITTEES = [{ id: "mrmc", label: "Model Risk Management Committee" }, { id: "fcmoc", label: "Financial Crime Model Oversight Committee" },
  { id: "aigc", label: "AI Governance Committee" }];

export default function CommitteeReporting() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [tab, setTab] = useState("mrmc");
  const pack = useQuery({ queryKey: ["committee", tab], queryFn: () => api(`/committees/${tab}`) });
  const hist = useQuery({ queryKey: ["reports"], queryFn: () => api("/reports") });
  const gen = useMutation({ mutationFn: (t: string) => api("/reports", { body: { report_type: t } }),
    onSuccess: async (r) => { qc.invalidateQueries({ queryKey: ["reports"] }); await download(`/reports/${r.report_id}/download`, r.file_name); } });
  const p = pack.data;
  return (
    <div className="space-y-4">
      <Panel bodyClass="flex flex-wrap items-center gap-2 p-3">
        <span className="text-[12.5px] text-muted">Generate and download a PDF:</span>
        {can("report:generate") && [["executive", "Executive report"], ["mrmc", "MRMC pack"], ["fcmoc", "FCMOC pack"], ["aigc", "AIGC pack"]].map(([t, l]) => (
          <button key={t} className={t === "executive" ? "btn-primary" : "btn-ghost"} disabled={gen.isPending} onClick={() => gen.mutate(t)}>{gen.isPending && gen.variables === t ? "Generating" : l}</button>))}
        <ErrorBox error={gen.error} />
      </Panel>
      <Tabs value={tab} onChange={setTab} tabs={COMMITTEES} />
      {pack.isLoading || !p ? <Spinner /> : (
        <div className="space-y-4">
          <Panel title={`${p.title} · as of ${date(p.as_of)}`}>
            <p className="text-[13.5px] leading-6">{p.summary}</p>
            <div className="mt-3"><div className="kv-k mb-1">Management recommendations</div>
              <ol className="list-decimal space-y-1 pl-5 text-[13px]">{p.recommendations.map((r: string, i: number) => <li key={i}>{r}</li>)}</ol></div>
          </Panel>
          {tab === "mrmc" && <MRMC p={p} />}
          {tab === "fcmoc" && <FCMOC p={p} />}
          {tab === "aigc" && <AIGC p={p} />}
          <Notice>{p.disclaimer}</Notice>
        </div>)}
      <Panel title="Report history" bodyClass="">
        <DataTable rowKey={(r: any) => r.report_id} rows={hist.data ?? []} empty="No reports generated yet."
          columns={[{ key: "id", header: "Report", render: (r: any) => <span className="font-medium whitespace-nowrap">{r.report_id}</span> },
            { key: "t", header: "Title", render: (r: any) => r.title }, { key: "a", header: "As of", render: (r: any) => date(r.as_of) },
            { key: "g", header: "Generated", render: (r: any) => <div className="text-[12px]"><div>{r.generated_by.full_name}</div><div className="text-muted">{dateTime(r.generated_at)}</div></div> },
            { key: "s", header: "Size", align: "right", render: (r: any) => `${num(r.file_size / 1024, 0)} KB` },
            { key: "h", header: "SHA-256", render: (r: any) => <code className="text-[11px]" title={r.sha256}>{r.sha256.slice(0, 16)}…</code> },
            { key: "d", header: "", render: (r: any) => <button className="text-accent hover:underline" onClick={() => download(`/reports/${r.report_id}/download`, r.file_name)}>Download</button> }]} />
      </Panel>
    </div>
  );
}

function MRMC({ p }: { p: any }) {
  return (<>
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Validation outcomes (last 12 months)" bodyClass="">
        <DataTable rowKey={(v: any) => v.validation_id} rows={p.validation_outcomes} columns={[
          { key: "v", header: "Validation", render: (v: any) => <Link className="font-medium hover:underline whitespace-nowrap" to={`/validations/${v.validation_id}`}>{v.validation_id}</Link> },
          { key: "m", header: "Model", className: "whitespace-nowrap", render: (v: any) => v.model_id }, { key: "s", header: "Decision", render: (v: any) => <StatusBadge s={v.status} /> },
          { key: "r", header: "Rating", render: (v: any) => v.rating }, { key: "d", header: "Decided", render: (v: any) => date(v.decided_on) }]} />
      </Panel>
      <Panel title="Validation pipeline" bodyClass="">
        <DataTable rowKey={(v: any) => v.validation_id} rows={p.validation_pipeline} columns={[
          { key: "v", header: "Validation", render: (v: any) => <Link className="font-medium hover:underline whitespace-nowrap" to={`/validations/${v.validation_id}`}>{v.validation_id}</Link> },
          { key: "m", header: "Model", className: "whitespace-nowrap", render: (v: any) => v.model_id }, { key: "s", header: "Status", render: (v: any) => <StatusBadge s={v.status} /> },
          { key: "l", header: "Lead", render: (v: any) => v.lead || "Not assigned" }, { key: "e", header: "Scheduled end", render: (v: any) => date(v.scheduled_end) }]} />
      </Panel>
    </div>
    <Panel title="Critical and High findings" bodyClass="">
      <DataTable rowKey={(f: any) => f.finding_id} rows={p.findings.critical_and_high_open} columns={[
        { key: "f", header: "Finding", render: (f: any) => <Link className="font-medium hover:underline whitespace-nowrap" to={`/findings/${f.finding_id}`}>{f.finding_id}</Link> },
        { key: "m", header: "Model", className: "whitespace-nowrap", render: (f: any) => f.model_id }, { key: "s", header: "Severity", render: (f: any) => <SeverityBadge s={f.severity} /> },
        { key: "t", header: "Title", render: (f: any) => f.title }, { key: "st", header: "Status", render: (f: any) => <StatusBadge s={f.status} /> },
        { key: "o", header: "Owner", render: (f: any) => f.owner }, { key: "d", header: "Target", render: (f: any) => <span className={f.overdue_days ? "text-bad" : ""}>{date(f.target_date)}</span> }]} />
    </Panel>
    <Panel title="Inventory changes (last 90 days, user actions)" bodyClass="">
      <DataTable rowKey={(c: any) => `${c.occurred_at}${c.entity}`} rows={p.inventory_changes} empty="No user changes in the period."
        columns={[{ key: "d", header: "When", render: (c: any) => dateTime(c.occurred_at) }, { key: "a", header: "By", render: (c: any) => c.actor },
          { key: "x", header: "Change", render: (c: any) => c.action.replace(/_/g, " ").toLowerCase() }, { key: "e", header: "Model", className: "whitespace-nowrap", render: (c: any) => c.entity },
          { key: "s", header: "Summary", render: (c: any) => c.summary }]} />
    </Panel>
  </>);
}

function FCMOC({ p }: { p: any }) {
  return (<>
    <Panel title="Model performance, latest period" bodyClass="">
      <DataTable rowKey={(r: any) => r.model_id} rows={p.monitoring} columns={[
        { key: "m", header: "Model", render: (r: any) => <Link className="font-medium hover:underline whitespace-nowrap" to={`/monitoring/${r.model_id}`}>{r.model_id}</Link> },
        { key: "s", header: "Status", render: (r: any) => <StatusBadge s={r.status} /> }, { key: "n", header: "Records", align: "right", render: (r: any) => num(r.records) },
        { key: "a", header: "Alerts", align: "right", render: (r: any) => (r.alerting ? num(r.alerts) : "n/a") },
        ...["precision", "recall", "psi", "dq_exception_rate"].map((k) => ({ key: k, header: k === "dq_exception_rate" ? "DQ exc." : k === "psi" ? "PSI" : k[0].toUpperCase() + k.slice(1), align: "right" as const,
          render: (r: any) => { const m = r.metrics[k]; return m ? <span className={m.status === "Breach" ? "font-medium text-bad" : m.status === "Warning" ? "text-warn" : ""}>{k === "psi" ? dec(m.value) : pct(m.value)}</span> : "–"; } })),
        { key: "d", header: "Drifting inputs", render: (r: any) => <span className="text-[12px]">{r.drifting_features.map((f: any) => f.feature).join(", ") || "–"}</span> }]} />
    </Panel>
    <Panel title="3 NYCRR Part 504 controls" bodyClass="">
      <DataTable rowKey={(c: any) => c.control_id} rows={p.part504_controls} columns={[{ key: "c", header: "Control", render: (c: any) => <span className="font-medium">{c.control_id} {c.name}</span> },
        { key: "s", header: "Status", render: (c: any) => <StatusBadge s={c.status} /> }, { key: "t", header: "Latest test", render: (c: any) => <StatusBadge s={c.latest_test} /> },
        { key: "g", header: "Gaps", render: (c: any) => <span className="text-[12px] text-muted">{c.gaps || "–"}</span> }]} />
    </Panel>
  </>);
}

function AIGC({ p }: { p: any }) {
  return (<>
    <Panel title="AI systems" bodyClass="">
      <DataTable rowKey={(s: any) => s.system_id} rows={p.systems} columns={[{ key: "s", header: "System", render: (s: any) => <Link className="font-medium hover:underline" to={`/ai/${s.system_id}`}>{s.system_id} {s.name}</Link> },
        { key: "c", header: "EU AI Act (readiness view)", render: (s: any) => <span className="text-[12px]">{s.classification}</span> }, { key: "a", header: "Approval", render: (s: any) => <StatusBadge s={s.approval} /> },
        { key: "d", header: "Deployment", render: (s: any) => <StatusBadge s={s.deployment} /> }, { key: "o", header: "Oversight", render: (s: any) => s.oversight },
        { key: "b", header: "Bias test", render: (s: any) => <StatusBadge s={s.bias} /> }]} />
    </Panel>
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="LLM evaluation runs" bodyClass="">
        <DataTable rowKey={(e: any) => e.run_id} rows={p.evaluations} columns={[{ key: "r", header: "Run", className: "whitespace-nowrap", render: (e: any) => e.run_id }, { key: "s", header: "System", render: (e: any) => e.system_id },
          { key: "v", header: "Version", render: (e: any) => e.version }, { key: "h", header: "Hallucination", align: "right", render: (e: any) => pct(e.metrics.hallucination_rate) },
          { key: "res", header: "Result", render: (e: any) => <><StatusBadge s={e.passed ? "Pass" : "Fail"} /> {e.breaches.map((b: string) => <Badge key={b} tone="red">{b}</Badge>)}</> }]} />
      </Panel>
      <Panel title="AI governance controls" bodyClass="">
        <DataTable rowKey={(c: any) => c.control_id} rows={p.ai_controls} columns={[{ key: "c", header: "Control", render: (c: any) => <span className="font-medium">{c.control_id} {c.name}</span> },
          { key: "s", header: "Status", render: (c: any) => <StatusBadge s={c.status} /> }, { key: "t", header: "Test", render: (c: any) => <StatusBadge s={c.latest_test} /> }]} />
      </Panel>
    </div>
  </>);
}
