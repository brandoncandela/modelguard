import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { ActionButton, Badge, Drawer, ErrorBox, Field, KV, Modal, Notice, Panel, RiskBadge, SeverityBadge, Spinner,
  StatusBadge, Stepper, Timeline } from "../components/ui";
import { date, dateTime } from "../lib/format";

const FLOW = ["Not Started", "Scheduled", "In Progress", "Pending Review"];
const ACTION_LABEL: Record<string, string> = {
  "Not Started": "Unschedule", Scheduled: "Schedule", "In Progress": "Start fieldwork", "Pending Review": "Submit for review",
  Approved: "Approve", "Conditionally Approved": "Approve with conditions", Rejected: "Reject",
};

export default function ValidationManagement() {
  const { validationId } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const [status, setStatus] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const meta = useQuery({ queryKey: ["val-meta"], queryFn: () => api("/validations/meta") });
  const list = useQuery({ queryKey: ["validations", "all"], queryFn: () => api("/validations") });
  const rows = (list.data ?? []).filter((v: any) => !status || v.status === status);
  const counts: Record<string, number> = {};
  (list.data ?? []).forEach((v: any) => (counts[v.status] = (counts[v.status] ?? 0) + 1));
  return (
    <div className="space-y-4">
      <Panel bodyClass="flex flex-wrap items-center gap-2 p-3">
        <button className={`btn-ghost ${!status ? "border-accent text-accent" : ""}`} onClick={() => setStatus("")}>All {list.data?.length ?? ""}</button>
        {(meta.data?.statuses ?? []).map((s: string) => (
          <button key={s} className={`btn-ghost ${status === s ? "border-accent text-accent" : ""}`} onClick={() => setStatus(s)}>{s} <span className="text-muted">{counts[s] ?? 0}</span></button>))}
        {can("validation:schedule") && <button className="btn-primary ml-auto" onClick={() => setCreating(true)}>New validation</button>}
      </Panel>
      <Panel bodyClass="">
        {list.isLoading ? <Spinner /> : (
          <DataTable rowKey={(v: any) => v.validation_id} rows={rows} onRowClick={(v: any) => nav(`/validations/${v.validation_id}`)}
            initialSort={{ key: "id", dir: "desc" }}
            columns={[
              { key: "id", header: "Validation", sort: (v: any) => v.validation_id, render: (v: any) => <span className="font-medium whitespace-nowrap">{v.validation_id}</span> },
              { key: "m", header: "Model", sort: (v: any) => v.model.model_id, render: (v: any) => <div><div className="whitespace-nowrap">{v.model.model_id}</div><div className="text-[12px] text-muted">{v.model.name}</div></div> },
              { key: "r", header: "Risk", render: (v: any) => <RiskBadge r={v.model.risk_rating} /> },
              { key: "t", header: "Type", render: (v: any) => v.validation_type },
              { key: "s", header: "Status", sort: (v: any) => v.status, render: (v: any) => <StatusBadge s={v.status} /> },
              { key: "l", header: "Lead validator", render: (v: any) => v.lead_validator?.full_name ?? <span className="text-muted">Not assigned</span> },
              { key: "sch", header: "Schedule", sort: (v: any) => v.scheduled_end, render: (v: any) => v.scheduled_start ? (
                <span className={v.schedule_overdue ? "text-bad" : ""}>{date(v.scheduled_start)} to {date(v.scheduled_end)}</span>) : <span className="text-muted">–</span> },
              { key: "rt", header: "Rating", render: (v: any) => v.overall_rating ?? <span className="text-muted">–</span> },
              { key: "f", header: "Findings", align: "right", sort: (v: any) => v.findings_open, render: (v: any) => <span>{v.findings_open} open / {v.findings_total}</span> },
            ]} />)}
      </Panel>
      {validationId && meta.data && <ValidationDrawer id={validationId} meta={meta.data} onClose={() => nav("/validations")} />}
      {creating && meta.data && <NewValidation meta={meta.data} onClose={() => setCreating(false)} onDone={(id) => { setCreating(false); nav(`/validations/${id}`); }} />}
    </div>
  );
}

function useValidators() {
  return useQuery({ queryKey: ["users", "validator"], queryFn: () => api("/users", { query: { role: "validator" } }) });
}

function NewValidation({ meta, onClose, onDone }: { meta: any; onClose: () => void; onDone: (id: string) => void }) {
  const models = useQuery({ queryKey: ["models", "all-min"], queryFn: () => api("/models", { query: { page_size: 200 } }) });
  const validators = useValidators();
  const [v, setV] = useState<any>({ model_id: "", validation_type: "Periodic", scope_areas: [], scope_notes: "", lead_validator_id: "", team: [], scheduled_start: "", scheduled_end: "" });
  const [err, setErr] = useState<unknown>(null);
  const set = (k: string, x: unknown) => setV((s: any) => ({ ...s, [k]: x }));
  const save = async () => {
    try {
      const r = await api("/validations", { body: { ...v, lead_validator_id: v.lead_validator_id ? Number(v.lead_validator_id) : null,
        scheduled_start: v.scheduled_start || null, scheduled_end: v.scheduled_end || null } });
      onDone(r.validation_id);
    } catch (e) { setErr(e); }
  };
  return (
    <Modal open onClose={onClose} title="New validation" footer={<><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save}>Create</button></>}>
      <Field label="Model"><select className="input" value={v.model_id} onChange={(e) => set("model_id", e.target.value)}>
        <option value="">Select a model</option>{(models.data?.items ?? []).map((m: any) => <option key={m.model_id} value={m.model_id}>{m.model_id} {m.name}</option>)}</select></Field>
      <Field label="Type"><select className="input" value={v.validation_type} onChange={(e) => set("validation_type", e.target.value)}>{meta.types.map((t: string) => <option key={t}>{t}</option>)}</select></Field>
      <ScopePicker areas={meta.scope_areas} value={v.scope_areas} onChange={(x) => set("scope_areas", x)} />
      <Field label="Scope notes"><textarea className="textarea" rows={2} value={v.scope_notes} onChange={(e) => set("scope_notes", e.target.value)} /></Field>
      <Field label="Lead validator" hint="Must not own the model"><select className="input" value={v.lead_validator_id} onChange={(e) => set("lead_validator_id", e.target.value)}>
        <option value="">Assign later</option>{(validators.data ?? []).map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Start"><input className="input" type="date" value={v.scheduled_start} onChange={(e) => set("scheduled_start", e.target.value)} /></Field>
        <Field label="End"><input className="input" type="date" value={v.scheduled_end} onChange={(e) => set("scheduled_end", e.target.value)} /></Field>
      </div>
      <ErrorBox error={err} />
    </Modal>
  );
}

function ScopePicker({ areas, value, onChange, disabled }: { areas: string[]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  return (
    <div><span className="label">Scope areas</span>
      <div className="grid gap-1 sm:grid-cols-2">{areas.map((a) => (
        <label key={a} className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" disabled={disabled} checked={value.includes(a)}
          onChange={(e) => onChange(e.target.checked ? [...value, a] : value.filter((x) => x !== a))} />{a}</label>))}</div>
    </div>
  );
}

function ValidationDrawer({ id, meta, onClose }: { id: string; meta: any; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { user, can } = useAuth();
  const q = useQuery({ queryKey: ["validation", id], queryFn: () => api(`/validations/${id}`) });
  const validators = useValidators();
  const [edit, setEdit] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busyReport, setBusyReport] = useState(false);
  const v = q.data;
  useEffect(() => {
    if (v) setEdit({ scope_areas: v.scope_areas, scope_notes: v.scope_notes, lead_validator_id: v.lead_validator?.id ?? "", team: v.team.map((t: any) => t.id),
      scheduled_start: v.scheduled_start ?? "", scheduled_end: v.scheduled_end ?? "", overall_rating: v.overall_rating ?? "", summary: v.summary,
      independence_attested: v.independence_attested, independence_statement: v.independence_statement });
  }, [v]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["validation", id] }); qc.invalidateQueries({ queryKey: ["validations"] }); };
  if (q.isLoading || !v || !edit) return <Drawer open onClose={onClose} title={id}><Spinner /></Drawer>;
  const planning = ["Not Started", "Scheduled"].includes(v.status) && ["admin", "compliance_reviewer"].includes(user!.role);
  const attest = v.status === "Scheduled" && user!.id === v.lead_validator?.id;
  const fieldwork = v.status === "In Progress" && (v.team.some((t: any) => t.id === user!.id) || v.lead_validator?.id === user!.id || user!.role === "admin");
  const patch = async (fields: string[]) => {
    setErr(null);
    const body: any = {};
    fields.forEach((f) => (body[f] = edit[f] === "" ? null : edit[f]));
    if ("lead_validator_id" in body && body.lead_validator_id) body.lead_validator_id = Number(body.lead_validator_id);
    try { await api(`/validations/${id}`, { method: "PATCH", body }); refresh(); } catch (e) { setErr(e); }
  };
  const transition = (to: string) => (comment: string, vals: Record<string, string>) =>
    api(`/validations/${id}/transition`, { body: { to_status: to, comment, conditions: vals.conditions ?? "" } }).then(refresh);
  const report = async () => {
    setBusyReport(true);
    try {
      const r = await api(`/validations/${id}/report`, { method: "POST" });
      await download(`/reports/${r.report_id}/download`, r.file_name);
    } catch (e) { setErr(e); } finally { setBusyReport(false); }
  };
  const set = (k: string, x: unknown) => setEdit((s: any) => ({ ...s, [k]: x }));
  const decided = ["Approved", "Conditionally Approved", "Rejected"].includes(v.status);
  return (
    <Drawer open onClose={onClose} width="max-w-4xl" title={
      <div><div className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold">{v.validation_id}</span><StatusBadge s={v.status} /><Badge>{v.validation_type}</Badge></div>
        <div className="text-[13px] text-muted"><Link className="hover:underline" to={`/inventory/${v.model.model_id}`}>{v.model.model_id}</Link> {v.model.name}</div></div>}>
      <div className="space-y-4 p-5">
        <Stepper steps={[...FLOW, decided ? v.status : "Decision"]} current={v.status} />
        <div className="flex flex-wrap gap-2">
          {v.actions.map((to: string) => {
            const isDecision = ["Approved", "Conditionally Approved", "Rejected"].includes(to);
            const rework = v.status === "Pending Review" && to === "In Progress";
            return (
              <ActionButton key={to} label={rework ? "Return for rework" : ACTION_LABEL[to] ?? to}
                tone={to === "Rejected" ? "danger" : isDecision || to === "Pending Review" ? "primary" : "ghost"}
                commentLabel={isDecision || rework ? "Comment" : ""} minComment={to === "Rejected" || rework ? 10 : 0}
                extra={to === "Conditionally Approved" ? (s, vals) => (
                  <Field label="Conditions of approval" hint="At least 20 characters"><textarea className="textarea" rows={3} value={vals.conditions ?? ""} onChange={(e) => s("conditions", e.target.value)} /></Field>) : undefined}
                onRun={transition(to)} />);
          })}
          {can("report:generate") && <button className="btn-ghost" disabled={busyReport} onClick={report}>{busyReport ? "Generating" : "Validation report (PDF)"}</button>}
        </div>
        {v.status === "Pending Review" && v.actions.includes("Approved") && v.findings.some((f: any) => ["Critical", "High"].includes(f.severity) && !["Closed", "Risk Accepted"].includes(f.status)) && (
          <Notice>Open Critical or High findings block full approval. Use Conditionally Approved with written conditions, or close them first.</Notice>)}
        <ErrorBox error={err} />

        <Panel title="Scope, team and schedule" actions={planning ? <button className="btn-primary h-7" onClick={() => patch(["scope_areas", "scope_notes", "lead_validator_id", "scheduled_start", "scheduled_end"])}>Save planning</button> : null}>
          <div className="space-y-3">
            <ScopePicker areas={meta.scope_areas} value={edit.scope_areas} onChange={(x) => set("scope_areas", x)} disabled={!planning} />
            <Field label="Scope notes"><textarea className="textarea" rows={2} disabled={!planning && !fieldwork} value={edit.scope_notes} onChange={(e) => set("scope_notes", e.target.value)} /></Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Lead validator"><select className="input" disabled={!planning} value={edit.lead_validator_id} onChange={(e) => set("lead_validator_id", e.target.value)}>
                <option value="">Not assigned</option>{(validators.data ?? []).map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
              <Field label="Start"><input className="input" type="date" disabled={!planning} value={edit.scheduled_start} onChange={(e) => set("scheduled_start", e.target.value)} /></Field>
              <Field label="End"><input className="input" type="date" disabled={!planning} value={edit.scheduled_end} onChange={(e) => set("scheduled_end", e.target.value)} /></Field>
            </div>
            <KV cols={3} items={[["Team", v.team.map((t: any) => t.full_name).join(", ") || "Lead only"], ["Fieldwork started", date(v.actual_start)], ["Submitted", date(v.submitted_on)]]} />
          </div>
        </Panel>

        <Panel title="Independence" actions={attest ? <button className="btn-primary h-7" onClick={() => patch(["independence_attested", "independence_statement"])}>Save attestation</button> : null}>
          <label className="flex items-center gap-2"><input type="checkbox" disabled={!attest && !fieldwork} checked={edit.independence_attested} onChange={(e) => set("independence_attested", e.target.checked)} />
            I have no role in developing, owning or using this model and report outside its business line.</label>
          <textarea className="textarea mt-2" rows={2} disabled={!attest && !fieldwork} placeholder="Independence statement" value={edit.independence_statement} onChange={(e) => set("independence_statement", e.target.value)} />
        </Panel>

        <Panel title="Conclusion" actions={fieldwork ? <button className="btn-primary h-7" onClick={() => patch(["overall_rating", "summary", "scope_notes"])}>Save conclusion</button> : null}>
          <div className="space-y-3">
            <Field label="Overall rating"><select className="input" disabled={!fieldwork} value={edit.overall_rating} onChange={(e) => set("overall_rating", e.target.value)}>
              <option value="">Not rated</option>{meta.ratings.map((r: string) => <option key={r}>{r}</option>)}</select></Field>
            <Field label="Summary"><textarea className="textarea" rows={4} disabled={!fieldwork} value={edit.summary} onChange={(e) => set("summary", e.target.value)} /></Field>
            {v.conditions && <KV cols={2} items={[["Conditions of approval", v.conditions]]} />}
          </div>
        </Panel>

        <Panel title={`Findings (${v.findings.length})`} bodyClass="" actions={v.can_raise_findings && can("finding:create") ? <RaiseFinding id={id} meta={meta} onDone={refresh} /> : null}>
          <DataTable rowKey={(f: any) => f.finding_id} rows={v.findings} empty="No findings raised." onRowClick={(f: any) => nav(`/findings/${f.finding_id}`)}
            columns={[{ key: "id", header: "Finding", render: (f: any) => <span className="font-medium whitespace-nowrap">{f.finding_id}</span> },
              { key: "sev", header: "Severity", render: (f: any) => <SeverityBadge s={f.severity} /> },
              { key: "t", header: "Title", render: (f: any) => f.title }, { key: "s", header: "Status", render: (f: any) => <StatusBadge s={f.status} /> },
              { key: "d", header: "Target", render: (f: any) => <span className={f.overdue ? "text-bad" : ""}>{date(f.target_date)}</span> }]} />
        </Panel>

        <EvidencePanel items={v.evidence} canAdd={v.can_add_evidence} uploadPath={`/validations/${id}/evidence`} onDone={refresh} />

        {v.approvals.length > 0 && (
          <Panel title="Approval record" bodyClass="">
            <DataTable rowKey={(a: any) => a.decided_at} rows={v.approvals} columns={[
              { key: "a", header: "Approver", render: (a: any) => `${a.approver.full_name}, ${a.approver.title}` },
              { key: "d", header: "Decision", render: (a: any) => <StatusBadge s={a.decision} /> },
              { key: "t", header: "Date", render: (a: any) => dateTime(a.decided_at) },
              { key: "c", header: "Comments", render: (a: any) => <span className="text-[12.5px]">{a.comments}{a.conditions ? ` Conditions: ${a.conditions}` : ""}</span> }]} />
          </Panel>)}

        <Panel title="Workflow history">
          <Timeline items={v.history.map((h: any) => ({ when: dateTime(h.occurred_at), who: h.actor.full_name,
            title: h.event_type === "STATUS_CHANGE" ? `${h.from_status} → ${h.to_status}` : h.event_type === "CREATED" ? "Created" : "Updated",
            body: h.comment || (h.data && Object.keys(h.data).length ? <code className="text-[11px]">{Object.keys(h.data).join(", ")}</code> : null) }))} />
        </Panel>
      </div>
    </Drawer>
  );
}

function RaiseFinding({ id, meta, onDone }: { id: string; meta: any; onDone: () => void }) {
  return (
    <ActionButton label="Raise finding" tone="primary" title="Raise a finding"
      extra={(s, vals) => (<>
        <Field label="Title"><input className="input" value={vals.title ?? ""} onChange={(e) => s("title", e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Severity"><select className="input" value={vals.severity ?? ""} onChange={(e) => s("severity", e.target.value)}>
            <option value="">Select</option>{meta.severities.map((x: string) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Category"><select className="input" value={vals.category ?? ""} onChange={(e) => s("category", e.target.value)}>
            <option value="">Select</option>{meta.categories.map((x: string) => <option key={x}>{x}</option>)}</select></Field>
        </div>
        <Field label="Description" hint="At least 20 characters. Target date defaults by severity under MRM-POL-001.">
          <textarea className="textarea" rows={4} value={vals.description ?? ""} onChange={(e) => s("description", e.target.value)} /></Field>
      </>)}
      onRun={(_, vals) => api(`/validations/${id}/findings`, { body: { title: vals.title, severity: vals.severity, category: vals.category, description: vals.description } }).then(onDone)} />
  );
}

export function EvidencePanel({ items, canAdd, uploadPath, onDone }: { items: any[]; canAdd: boolean; uploadPath: string; onDone: () => void }) {
  return (
    <Panel title={`Evidence (${items.length})`} bodyClass="" actions={canAdd ? (
      <ActionButton label="Add evidence" tone="primary" title="Add evidence"
        extra={(s, vals) => (<>
          <Field label="Title"><input className="input" value={vals.title ?? ""} onChange={(e) => s("title", e.target.value)} /></Field>
          <Field label="Evidence type"><input className="input" placeholder="Test results, data extract, memo" value={vals.type ?? ""} onChange={(e) => s("type", e.target.value)} /></Field>
          <Field label="Description"><textarea className="textarea" rows={2} value={vals.description ?? ""} onChange={(e) => s("description", e.target.value)} /></Field>
          <Field label="File (optional)" hint="PDF, CSV, TXT, JSON, PNG, JPG, XLSX or DOCX up to 10 MB. The SHA-256 is recorded.">
            <input type="file" id="evidence-file" className="text-[12.5px]" /></Field>
        </>)}
        onRun={async (_, vals) => {
          const fd = new FormData();
          fd.append("title", vals.title ?? "");
          fd.append("evidence_type", vals.type ?? "");
          fd.append("description", vals.description ?? "");
          const file = (document.getElementById("evidence-file") as HTMLInputElement | null)?.files?.[0];
          if (file) fd.append("file", file);
          await api(uploadPath, { form: fd, method: "POST" });
          onDone();
        }} />) : null}>
      <DataTable rowKey={(e: any) => e.evidence_id} rows={items} empty="No evidence attached."
        columns={[{ key: "id", header: "ID", render: (e: any) => <span className="font-medium whitespace-nowrap">{e.evidence_id}</span> },
          { key: "t", header: "Title", render: (e: any) => <div><div>{e.title}</div><div className="text-[11.5px] text-muted">{e.evidence_type}</div></div> },
          { key: "f", header: "File", render: (e: any) => e.has_file ? (
            <button className="text-accent hover:underline" onClick={(ev) => { ev.stopPropagation(); download(`/evidence/${e.evidence_id}/download`, e.file_name); }}>{e.file_name}</button>) : <span className="text-muted">Reference only</span> },
          { key: "h", header: "SHA-256", render: (e: any) => e.sha256 ? <code className="text-[11px]" title={e.sha256}>{e.sha256.slice(0, 12)}…</code> : "–" },
          { key: "u", header: "Added", render: (e: any) => <div className="text-[12px]"><div>{e.uploaded_by.full_name}</div><div className="text-muted">{dateTime(e.uploaded_at)}</div></div> }]} />
    </Panel>
  );
}
