import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { ActionButton, Badge, Drawer, Field, KV, Kpi, Panel, SeverityBadge, Spinner, StatusBadge, Stepper,
  Timeline } from "../components/ui";
import { COLORS, Plot } from "../components/charts/Plot";
import { date, dateTime } from "../lib/format";
import { EvidencePanel } from "./ValidationManagement";

const FLOW = ["Open", "Response Submitted", "In Remediation", "Pending Validation", "Closed"];

export default function FindingsRemediation() {
  const { findingId } = useParams();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const { user } = useAuth();
  const [sev, setSev] = useState(sp.get("severity") ?? "");
  const [status, setStatus] = useState("open");
  const [mine, setMine] = useState(false);
  const sum = useQuery({ queryKey: ["findings-summary"], queryFn: () => api("/findings/summary") });
  const list = useQuery({ queryKey: ["findings", sev, status, mine], queryFn: () => api("/findings", { query: {
    severity: sev ? [sev] : undefined, open_only: status === "open", overdue: status === "overdue" ? true : undefined,
    status: !["open", "overdue", "all"].includes(status) ? [status] : undefined, owner: mine ? user?.username : undefined } }) });
  const s = sum.data;
  return (
    <div className="space-y-4">
      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Kpi label="Open findings" value={s.open} note={`of ${s.total} raised`} onClick={() => setStatus("open")} />
          <Kpi label="Past target" value={s.overdue} tone={s.overdue ? "bad" : "ok"} note="open and overdue" onClick={() => setStatus("overdue")} />
          <Kpi label="Open Critical" value={s.open_critical} tone={s.open_critical ? "bad" : "ok"} onClick={() => { setSev("Critical"); setStatus("open"); }} />
          <Kpi label="Open High" value={s.open_high} tone={s.open_high ? "warn" : "ok"} onClick={() => { setSev("High"); setStatus("open"); }} />
          <Kpi label="Closed" value={s.closed} note={`${s.closed_on_time} within target`} onClick={() => setStatus("Closed")} />
          <Kpi label="Risk accepted" value={s.risk_accepted} note="with expiry dates" onClick={() => setStatus("Risk Accepted")} />
        </div>)}
      {s && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel title="Open findings by days past target">
            <Plot ariaLabel="Bar chart of open findings by aging bucket" height={220} data={[{ type: "bar", x: Object.keys(s.aging), y: Object.values(s.aging),
              marker: { color: [COLORS.teal, COLORS.amber, COLORS.orange, COLORS.red] } }]} layout={{ yaxis: { dtick: 1, gridcolor: "#EEF2F7" } }} />
          </Panel>
          <Panel title="Findings by severity and status">
            <Plot ariaLabel="Stacked bar chart of findings by severity and status" height={220}
              data={s.statuses.map((st: string, i: number) => ({ type: "bar", name: st, x: s.severities, y: s.severities.map((sv: string) => s.by_severity_status[sv]?.[st] ?? 0),
                marker: { color: [COLORS.red, COLORS.amber, COLORS.accent, COLORS.light, COLORS.teal, COLORS.slate][i] } }))}
              layout={{ barmode: "stack", yaxis: { dtick: 2, gridcolor: "#EEF2F7" } }} />
          </Panel>
        </div>)}
      <Panel bodyClass="flex flex-wrap items-end gap-2 p-3">
        <div className="w-40"><Field label="Severity"><select className="input" value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">All</option>{["Critical", "High", "Medium", "Low"].map((x) => <option key={x}>{x}</option>)}</select></Field></div>
        <div className="w-48"><Field label="Status"><select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="open">Open (any stage)</option><option value="overdue">Past target</option><option value="all">All</option>
          {(s?.statuses ?? []).map((x: string) => <option key={x}>{x}</option>)}</select></Field></div>
        <label className="flex h-8 items-center gap-2 text-[12.5px]"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Assigned to me</label>
      </Panel>
      <Panel bodyClass="">
        {list.isLoading ? <Spinner /> : (
          <DataTable rowKey={(f: any) => f.finding_id} rows={list.data ?? []} onRowClick={(f: any) => nav(`/findings/${f.finding_id}`)} empty="No findings match."
            columns={[
              { key: "id", header: "Finding", sort: (f: any) => f.finding_id, render: (f: any) => <span className="font-medium whitespace-nowrap">{f.finding_id}</span> },
              { key: "sev", header: "Severity", sort: (f: any) => ["Low", "Medium", "High", "Critical"].indexOf(f.severity), render: (f: any) => <SeverityBadge s={f.severity} /> },
              { key: "t", header: "Title", render: (f: any) => <div className="min-w-[260px]"><div>{f.title}</div><div className="text-[11.5px] text-muted">{f.model.model_id} · {f.category} · {f.validation_id}</div></div> },
              { key: "s", header: "Status", sort: (f: any) => f.status, render: (f: any) => <StatusBadge s={f.status} /> },
              { key: "o", header: "Owner", render: (f: any) => f.remediation_owner?.full_name ?? "–" },
              { key: "d", header: "Target", sort: (f: any) => f.target_date, render: (f: any) => (
                <div className="whitespace-nowrap"><div className={f.overdue ? "font-medium text-bad" : ""}>{date(f.target_date)}</div>
                  {f.overdue ? <div className="text-[11.5px] text-bad">{f.days_overdue} days past</div> : f.extension_count ? <div className="text-[11.5px] text-muted">{f.extension_count} extension{f.extension_count > 1 ? "s" : ""}</div> : null}</div>) },
              { key: "a", header: "Age", align: "right", sort: (f: any) => f.age_days, render: (f: any) => `${f.age_days}d` },
            ]} />)}
      </Panel>
      {findingId && <FindingDrawer id={findingId} onClose={() => nav("/findings")} />}
    </div>
  );
}

function FindingDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["finding", id], queryFn: () => api(`/findings/${id}`) });
  const owners = useQuery({ queryKey: ["users", "owners"], queryFn: () => api("/users", { query: { role: "model_owner" } }) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["finding", id] }); qc.invalidateQueries({ queryKey: ["findings"] }); qc.invalidateQueries({ queryKey: ["findings-summary"] }); };
  const f = q.data;
  if (q.isLoading || !f) return <Drawer open onClose={onClose} title={id}><Spinner /></Drawer>;
  const tr = (to: string) => (c: string, vals: Record<string, string>) =>
    api(`/findings/${id}/transition`, { body: { to_status: to, comment: c, risk_acceptance_expiry: vals.expiry || null } }).then(refresh);
  const label: Record<string, string> = { "In Remediation": f.status === "Pending Validation" ? "Reject remediation" : "Accept action plan",
    Open: "Reject response", "Pending Validation": "Submit remediation for validation", Closed: "Verify and close", "Risk Accepted": "Accept risk" };
  return (
    <Drawer open onClose={onClose} width="max-w-3xl" title={
      <div><div className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold">{f.finding_id}</span><SeverityBadge s={f.severity} /><StatusBadge s={f.status} />
        {f.overdue && <Badge tone="red">{f.days_overdue} days past target</Badge>}</div>
        <div className="text-[13px] text-muted">{f.title}</div></div>}>
      <div className="space-y-4 p-5">
        <Stepper steps={FLOW} current={f.status} terminal={f.status === "Risk Accepted" ? "Risk Accepted" : undefined} />
        <div className="flex flex-wrap gap-2">
          {f.actions.includes("respond") && (
            <ActionButton label={f.status === "Open" ? "Submit management response" : "Revise response"} tone="primary" title="Management response"
              extra={(s, v) => (<>
                <Field label="Management response"><textarea className="textarea" rows={3} value={v.response ?? f.management_response ?? ""} onChange={(e) => s("response", e.target.value)} /></Field>
                <Field label="Action plan"><textarea className="textarea" rows={3} value={v.plan ?? f.action_plan ?? ""} onChange={(e) => s("plan", e.target.value)} /></Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Remediation owner"><select className="input" value={v.owner ?? f.remediation_owner?.id ?? ""} onChange={(e) => s("owner", e.target.value)}>
                    {(owners.data ?? []).map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
                  <Field label="Target date" hint={`Policy date ${date(f.original_target_date)}`}><input className="input" type="date" value={v.target ?? f.target_date ?? ""} onChange={(e) => s("target", e.target.value)} /></Field>
                </div>
              </>)}
              onRun={(_, v) => api(`/findings/${id}/response`, { body: { management_response: v.response ?? f.management_response, action_plan: v.plan ?? f.action_plan,
                remediation_owner_id: Number(v.owner ?? f.remediation_owner?.id), target_date: v.target ?? f.target_date } }).then(refresh)} />)}
          {f.actions.filter((a: string) => !["respond", "extend", "add_evidence"].includes(a)).map((to: string) => (
            <ActionButton key={to} label={label[to] ?? to} tone={to === "Closed" || to === "Pending Validation" || (to === "In Remediation" && f.status === "Response Submitted") ? "primary" : to === "Risk Accepted" ? "danger" : "ghost"}
              commentLabel={to === "Risk Accepted" ? "Risk acceptance rationale" : "Comment"} minComment={to === "Risk Accepted" ? 20 : ["Open"].includes(to) || (to === "In Remediation" && f.status === "Pending Validation") ? 10 : 0}
              extra={to === "Risk Accepted" ? (s, v) => <Field label="Acceptance expires" hint="Within 12 months; Critical findings cannot be accepted">
                <input className="input" type="date" value={v.expiry ?? ""} onChange={(e) => s("expiry", e.target.value)} /></Field> : undefined}
              onRun={tr(to)} />))}
          {f.actions.includes("extend") && (
            <ActionButton label="Extend target date" title="Extend target date" commentLabel="Justification" minComment={20}
              extra={(s, v) => <Field label="New target date"><input className="input" type="date" value={v.date ?? ""} onChange={(e) => s("date", e.target.value)} /></Field>}
              onRun={(c, v) => api(`/findings/${id}/extend`, { body: { new_target_date: v.date, justification: c } }).then(refresh)} />)}
        </div>
        <Panel title="Finding">
          <KV items={[["Model", <Link className="text-accent hover:underline" to={`/inventory/${f.model.model_id}`}>{f.model.model_id} {f.model.name}</Link>],
            ["Validation", <Link className="text-accent hover:underline" to={`/validations/${f.validation_id}`}>{f.validation_id}</Link>],
            ["Category", f.category], ["Raised", `${date(f.raised_on)} by ${f.raised_by.full_name}`], ["Remediation owner", f.remediation_owner?.full_name],
            ["Target", `${date(f.target_date)} (policy ${date(f.original_target_date)}, ${f.extension_count} extension${f.extension_count === 1 ? "" : "s"})`],
            ["Closed", f.closed_on ? `${date(f.closed_on)} by ${f.closed_by?.full_name}` : "–"], ["Age", `${f.age_days} days`]]} />
          <div className="mt-4 space-y-3 text-[13px] leading-5">
            <div><div className="kv-k mb-1">Description</div>{f.description}</div>
            {f.management_response && <div><div className="kv-k mb-1">Management response</div>{f.management_response}</div>}
            {f.action_plan && <div><div className="kv-k mb-1">Action plan</div>{f.action_plan}</div>}
            {f.risk_acceptance_rationale && <div><div className="kv-k mb-1">Risk acceptance (expires {date(f.risk_acceptance_expiry)})</div>{f.risk_acceptance_rationale}</div>}
          </div>
        </Panel>
        <EvidencePanel items={f.evidence} canAdd={f.actions.includes("add_evidence") || f.actions.includes("Closed")} uploadPath={`/findings/${id}/evidence`} onDone={refresh} />
        <Panel title="Resolution history">
          <Timeline items={f.history.map((h: any) => ({ when: dateTime(h.occurred_at), who: h.actor.full_name,
            title: h.event_type === "STATUS_CHANGE" ? `${h.from_status} → ${h.to_status}` : h.event_type === "RAISED" ? "Raised" : h.event_type === "RESPONSE" ? "Management response submitted"
              : h.event_type === "EXTENSION" ? `Target date extended to ${h.data?.to ?? ""}` : h.event_type,
            body: h.comment }))} />
        </Panel>
      </div>
    </Drawer>
  );
}
