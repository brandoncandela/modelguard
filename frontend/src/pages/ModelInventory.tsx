import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { ActionButton, Badge, Drawer, Empty, ErrorBox, Field, KV, Modal, Panel, RiskBadge, Spinner, StatusBadge,
  Tabs, Timeline, useDebounced } from "../components/ui";
import { date, dateTime, fmtMetric, metricLabel } from "../lib/format";

const SHORT_CLASS: Record<string, string> = {
  "Model under SR 26-2": "Model",
  "Outside SR 26-2 definition (deterministic)": "Deterministic",
  "Outside SR 26-2 scope (generative AI)": "Generative AI",
};

export default function ModelInventory() {
  const { modelId } = useParams();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [f, setF] = useState<Record<string, string>>({ risk_rating: sp.get("risk") ?? "", validation_due: sp.get("due") ?? "" });
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q);
  const facets = useQuery({ queryKey: ["facets"], queryFn: () => api("/models/facets") });
  const list = useQuery({
    queryKey: ["models", dq, f, archived],
    queryFn: () => api("/models", { query: { q: dq, page_size: 200, archived_only: archived, ...f } }),
  });

  const setFilter = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));
  const fc = facets.data;
  return (
    <div className="space-y-4">
      <Panel bodyClass="p-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[220px] flex-1"><Field label="Search">
            <input className="input" placeholder="ID, name, methodology, limitations, owner" value={q} onChange={(e) => setQ(e.target.value)} />
          </Field></div>
          {fc && ([["category", "Category", fc.categories], ["risk_rating", "Risk", fc.risk_ratings], ["lifecycle_stage", "Lifecycle", fc.lifecycle_stages],
            ["approval_status", "Approval", fc.approval_statuses], ["documentation_status", "Documentation", fc.documentation_statuses]] as [string, string, string[]][]).map(([k, l, opts]) => (
            <div key={k} className="w-40"><Field label={l}>
              <select className="input" value={f[k] ?? ""} onChange={(e) => setFilter(k, e.target.value)}>
                <option value="">All</option>{opts.map((o) => <option key={o}>{o}</option>)}
              </select></Field></div>
          ))}
          <div className="w-40"><Field label="Validation due">
            <select className="input" value={f.validation_due ?? ""} onChange={(e) => setFilter("validation_due", e.target.value)}>
              <option value="">Any</option><option value="overdue">Overdue</option><option value="due_90d">Due in 90 days</option>
            </select></Field></div>
          <label className="flex h-8 items-center gap-2 text-[12.5px]"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Archived only</label>
          {can("inventory:create") && <button className="btn-primary ml-auto" onClick={() => setCreating(true)}>Register model</button>}
        </div>
      </Panel>

      <Panel title={list.data ? `${list.data.total} ${archived ? "archived " : ""}inventory entr${list.data.total === 1 ? "y" : "ies"}` : "Inventory"} bodyClass="">
        {list.isLoading ? <Spinner /> : list.error ? <div className="p-4"><ErrorBox error={list.error} /></div> : (
          <DataTable rowKey={(r: any) => r.model_id} rows={list.data.items} onRowClick={(r: any) => nav(`/inventory/${r.model_id}`)}
            initialSort={{ key: "id", dir: "asc" }}
            columns={[
              { key: "id", header: "Model", sort: (r: any) => r.model_id, render: (r: any) => (
                <div className="min-w-[220px]"><div className="font-medium whitespace-nowrap">{r.model_id}</div><div className="text-[12px] text-muted">{r.name}</div></div>) },
              { key: "cat", header: "Category / methodology", sort: (r: any) => r.category, render: (r: any) => (
                <div className="min-w-[170px]"><div>{r.category}</div><div className="text-[11.5px] text-muted">{r.methodology_type}</div></div>) },
              { key: "risk", header: "Risk", sort: (r: any) => ({ High: 3, Medium: 2, Low: 1 } as any)[r.risk_rating], render: (r: any) => <RiskBadge r={r.risk_rating} /> },
              { key: "class", header: "SR 26-2", render: (r: any) => <span title={r.supervisory_classification} className="text-[12px]">{SHORT_CLASS[r.supervisory_classification] ?? r.supervisory_classification}</span> },
              { key: "life", header: "Lifecycle", render: (r: any) => <StatusBadge s={r.lifecycle_stage} /> },
              { key: "appr", header: "Approval", render: (r: any) => <StatusBadge s={r.approval_status} /> },
              { key: "next", header: "Next validation", sort: (r: any) => r.next_validation_date, render: (r: any) => (
                <div className="whitespace-nowrap"><div className={r.validation_state === "Overdue" ? "font-medium text-bad" : ""}>{date(r.next_validation_date)}</div>
                  <div className="text-[11.5px] text-muted">{r.validation_state}</div></div>) },
              { key: "docs", header: "Docs", sort: (r: any) => r.documentation_completeness, render: (r: any) => (
                <div><StatusBadge s={r.documentation_status} /><div className="text-[11.5px] text-muted">{r.documentation_completeness}%</div></div>) },
              { key: "mon", header: "Monitoring", render: (r: any) => <StatusBadge s={r.monitoring_status} /> },
              { key: "fnd", header: "Open findings", align: "right", sort: (r: any) => r.open_findings, render: (r: any) => r.open_findings || <span className="text-muted">0</span> },
              { key: "own", header: "Owners", render: (r: any) => <div className="min-w-[130px] text-[12px]"><div>{r.business_owner.full_name}</div><div className="text-muted">{r.model_risk_owner.full_name}</div></div> },
            ]} />
        )}
      </Panel>

      {modelId && <ModelDrawer modelId={modelId} onClose={() => nav("/inventory")} />}
      {creating && fc && <ModelForm facets={fc} onClose={() => setCreating(false)} onSaved={(id) => { setCreating(false); nav(`/inventory/${id}`); }} />}
    </div>
  );
}

function ModelDrawer({ modelId, onClose }: { modelId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { can } = useAuth();
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(false);
  const m = useQuery({ queryKey: ["model", modelId], queryFn: () => api(`/models/${modelId}`) });
  const facets = useQuery({ queryKey: ["facets"], queryFn: () => api("/models/facets") });
  const hist = useQuery({ queryKey: ["model-history", modelId], queryFn: () => api(`/models/${modelId}/history`), enabled: tab === "history" });
  const vals = useQuery({ queryKey: ["validations", modelId], queryFn: () => api("/validations", { query: { model_id: modelId } }), enabled: tab === "validations" });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["models"] }); qc.invalidateQueries({ queryKey: ["model", modelId] }); qc.invalidateQueries({ queryKey: ["model-history", modelId] }); };
  const restore = useMutation({ mutationFn: () => api(`/models/${modelId}/restore`, { method: "POST" }), onSuccess: refresh });
  const d = m.data;
  return (
    <Drawer open onClose={onClose} width="max-w-4xl" title={d ? (
      <div>
        <div className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold">{d.model_id}</span><RiskBadge r={d.risk_rating} /><StatusBadge s={d.approval_status} />
          {d.is_archived && <Badge tone="slate">Archived</Badge>}</div>
        <div className="text-[13px] text-muted">{d.name}</div>
      </div>) : modelId}>
      {m.isLoading || !d ? <Spinner /> : (
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2">
            {d.can_edit && !d.is_archived && <button className="btn-ghost" onClick={() => setEditing(true)}>Edit</button>}
            {can("inventory:archive") && !d.is_archived && (
              <ActionButton label="Archive" tone="danger" commentLabel="Reason for archiving" minComment={10}
                onRun={(c) => api(`/models/${modelId}/archive`, { body: { reason: c } }).then(refresh)} />)}
            {can("inventory:archive") && d.is_archived && <button className="btn-ghost" onClick={() => restore.mutate()}>Restore</button>}
            <Link className="btn-ghost" to={`/monitoring/${d.model_id}`}>Monitoring</Link>
          </div>
          <ErrorBox error={restore.error} />
          <Tabs value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "thresholds", label: `Thresholds (${d.thresholds.length})` },
            { id: "validations", label: "Validations" }, { id: "history", label: "Change history" }]} />
          {tab === "overview" && (
            <div className="space-y-5">
              <KV items={[
                ["Business owner", `${d.business_owner.full_name}, ${d.business_owner.title}`], ["Model risk owner", `${d.model_risk_owner.full_name}, ${d.model_risk_owner.title}`],
                ["Business unit", d.business_unit], ["Category", d.category], ["Methodology type", d.methodology_type], ["Vendor", d.vendor],
                ["Version", d.version], ["Developer", d.developer], ["Geographies", d.geographies.join(", ")],
                ["Lifecycle stage", <StatusBadge s={d.lifecycle_stage} />], ["Implementation date", date(d.implementation_date)], ["Monitoring", d.monitoring_frequency],
                ["Last validation", date(d.last_validation_date)], ["Next validation", <span className={d.validation_state === "Overdue" ? "font-medium text-bad" : ""}>{date(d.next_validation_date)} · {d.validation_state}</span>],
                ["Open findings / breaches", `${d.open_findings} / ${d.open_breaches}`],
              ]} />
              <Section title="Methodology">{d.methodology}</Section>
              <Section title="Risk classification">{d.risk_rating}. {d.risk_rationale}</Section>
              <Section title="Classification under SR 26-2 / OCC 2026-13">
                <div className="mb-1"><Badge tone="blue">{d.supervisory_classification}</Badge></div>{d.classification_rationale}
              </Section>
              <Section title="Model limitations">{d.limitations || "None recorded"}</Section>
              <div>
                <div className="kv-k mb-1">Documentation · {d.documentation_status} · {d.documentation_completeness}% · reviewed {date(d.documentation_reviewed_on)}</div>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {Object.entries(d.documentation_checklist as Record<string, boolean>).map(([a, ok]) => (
                    <li key={a} className="flex items-center gap-2 text-[12.5px]"><span className={ok ? "text-ok" : "text-bad"}>{ok ? "✓" : "✕"}</span>{a}</li>))}
                </ul>
              </div>
            </div>)}
          {tab === "thresholds" && (
            <DataTable rowKey={(t: any) => t.metric} rows={d.thresholds} columns={[
              { key: "metric", header: "Metric", render: (t: any) => <span className="font-medium">{metricLabel[t.metric] ?? t.metric}</span> },
              { key: "kind", header: "Type", render: (t: any) => <Badge tone={t.kind === "KPI" ? "blue" : "slate"}>{t.kind}</Badge> },
              { key: "dir", header: "Adverse when", render: (t: any) => (t.direction === "min" ? "below limit" : "above limit") },
              { key: "w", header: "Warning", align: "right", render: (t: any) => fmtMetric(t.metric, t.warning_limit) },
              { key: "b", header: "Breach", align: "right", render: (t: any) => fmtMetric(t.metric, t.breach_limit) },
              { key: "r", header: "Rationale", render: (t: any) => <span className="text-[12px] text-muted">{t.rationale}</span> },
            ]} />)}
          {tab === "validations" && (vals.isLoading ? <Spinner /> : (
            <DataTable rowKey={(v: any) => v.validation_id} rows={vals.data ?? []} empty="No validations recorded."
              onRowClick={(v: any) => nav(`/validations/${v.validation_id}`)}
              columns={[{ key: "id", header: "Validation", render: (v: any) => <span className="font-medium whitespace-nowrap">{v.validation_id}</span> },
                { key: "t", header: "Type", render: (v: any) => v.validation_type }, { key: "s", header: "Status", render: (v: any) => <StatusBadge s={v.status} /> },
                { key: "r", header: "Rating", render: (v: any) => v.overall_rating ?? "–" }, { key: "d", header: "Decided", render: (v: any) => date(v.decided_on) },
                { key: "f", header: "Findings", align: "right", render: (v: any) => `${v.findings_open} open / ${v.findings_total}` }]} />))}
          {tab === "history" && (hist.isLoading ? <Spinner /> : (
            <Timeline items={(hist.data ?? []).map((h: any) => ({ when: dateTime(h.occurred_at), who: h.actor, title: h.action.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c: string) => c.toUpperCase()),
              body: <><div>{h.summary}</div>{h.changes && Object.keys(h.changes).length > 0 && (
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-sunken p-2 text-[11px]">{JSON.stringify(h.changes, null, 2)}</pre>)}</> }))} />))}
        </div>
      )}
      {editing && d && facets.data && <ModelForm facets={facets.data} model={d} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); refresh(); }} />}
    </Drawer>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div><div className="kv-k mb-1">{title}</div><div className="text-[13px] leading-5">{children}</div></div>;
}

function ModelForm({ facets, model, onClose, onSaved }: { facets: any; model?: any; onClose: () => void; onSaved: (id: string) => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const users = useQuery({ queryKey: ["users", "model_owner"], queryFn: () => api("/users") });
  const owners = useMemo(() => (users.data ?? []).filter((u: any) => ["model_owner", "admin"].includes(u.role)), [users.data]);
  const init = model ? {
    ...model, business_owner_id: model.business_owner.id, model_risk_owner_id: model.model_risk_owner.id,
    geographies: model.geographies.join(", "),
  } : {
    model_id: "", name: "", description: "", business_owner_id: user?.role === "model_owner" ? user.id : "", model_risk_owner_id: user?.role === "model_owner" ? user.id : "",
    business_unit: "", category: facets.categories[0], methodology_type: facets.methodology_types[0], methodology: "", vendor: "In-house", version: "1.0",
    developer: "", geographies: "", risk_rating: "Medium", risk_rationale: "", supervisory_classification: facets.supervisory_classifications[0],
    classification_rationale: "", lifecycle_stage: "Development", limitations: "", monitoring_frequency: "Monthly",
    documentation_checklist: Object.fromEntries(facets.documentation_artifacts.map((a: string) => [a, false])), documentation_reviewed_on: null,
  };
  const [v, setV] = useState<any>(init);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setErr(null), [v]);
  const set = (k: string, val: unknown) => setV((s: any) => ({ ...s, [k]: val }));
  const save = async () => {
    setBusy(true);
    const body: any = { ...v, geographies: String(v.geographies).split(",").map((s: string) => s.trim()).filter(Boolean),
      business_owner_id: Number(v.business_owner_id), model_risk_owner_id: Number(v.model_risk_owner_id) };
    for (const k of ["implementation_date", "last_validation_date", "next_validation_date", "documentation_reviewed_on"]) if (!body[k]) body[k] = null;
    try {
      if (model) {
        const allowed = ["name", "description", "business_owner_id", "model_risk_owner_id", "business_unit", "category", "methodology", "methodology_type",
          "vendor", "version", "developer", "geographies", "risk_rating", "risk_rationale", "supervisory_classification", "classification_rationale",
          "lifecycle_stage", "implementation_date", "documentation_checklist", "documentation_reviewed_on", "limitations", "monitoring_frequency",
          ...(isAdmin ? ["approval_status", "last_validation_date", "next_validation_date"] : [])];
        const patch = Object.fromEntries(allowed.map((k) => [k, body[k]]));
        await api(`/models/${model.model_id}`, { method: "PATCH", body: patch });
        onSaved(model.model_id);
      } else {
        const r = await api("/models", { body });
        onSaved(r.model_id);
      }
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  const sel = (k: string, opts: string[]) => <select className="input" value={v[k] ?? ""} onChange={(e) => set(k, e.target.value)}>{opts.map((o) => <option key={o}>{o}</option>)}</select>;
  return (
    <Modal open onClose={onClose} title={model ? `Edit ${model.model_id}` : "Register a model"}
      footer={<><button className="btn-ghost" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy} onClick={save}>{busy ? "Saving" : "Save"}</button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        {!model && <Field label="Model ID" hint="Format MDL-XXX-000"><input className="input" value={v.model_id} onChange={(e) => set("model_id", e.target.value.toUpperCase())} /></Field>}
        <Field label="Name"><input className="input" value={v.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Business owner"><select className="input" value={v.business_owner_id} onChange={(e) => set("business_owner_id", e.target.value)}>
          <option value="">Select</option>{owners.map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
        <Field label="Model risk owner"><select className="input" value={v.model_risk_owner_id} onChange={(e) => set("model_risk_owner_id", e.target.value)}>
          <option value="">Select</option>{owners.map((u: any) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
        <Field label="Business unit"><input className="input" value={v.business_unit} onChange={(e) => set("business_unit", e.target.value)} /></Field>
        <Field label="Category">{sel("category", facets.categories)}</Field>
        <Field label="Methodology type">{sel("methodology_type", facets.methodology_types)}</Field>
        <Field label="Risk rating">{sel("risk_rating", facets.risk_ratings)}</Field>
        <Field label="Lifecycle stage">{sel("lifecycle_stage", facets.lifecycle_stages)}</Field>
        <Field label="Monitoring frequency">{sel("monitoring_frequency", facets.monitoring_frequencies)}</Field>
        <Field label="SR 26-2 classification">{sel("supervisory_classification", facets.supervisory_classifications)}</Field>
        <Field label="Vendor"><input className="input" value={v.vendor} onChange={(e) => set("vendor", e.target.value)} /></Field>
        <Field label="Version"><input className="input" value={v.version} onChange={(e) => set("version", e.target.value)} /></Field>
        <Field label="Geographies" hint="Comma separated"><input className="input" value={v.geographies} onChange={(e) => set("geographies", e.target.value)} /></Field>
        <Field label="Implementation date"><input className="input" type="date" value={v.implementation_date ?? ""} onChange={(e) => set("implementation_date", e.target.value)} /></Field>
        {isAdmin && model && <>
          <Field label="Approval status">{sel("approval_status", facets.approval_statuses)}</Field>
          <Field label="Last validation"><input className="input" type="date" value={v.last_validation_date ?? ""} onChange={(e) => set("last_validation_date", e.target.value)} /></Field>
          <Field label="Next validation"><input className="input" type="date" value={v.next_validation_date ?? ""} onChange={(e) => set("next_validation_date", e.target.value)} /></Field>
        </>}
      </div>
      <Field label="Methodology"><textarea className="textarea" rows={3} value={v.methodology} onChange={(e) => set("methodology", e.target.value)} /></Field>
      <Field label="Risk rationale"><textarea className="textarea" rows={2} value={v.risk_rationale} onChange={(e) => set("risk_rationale", e.target.value)} /></Field>
      <Field label="Classification rationale"><textarea className="textarea" rows={2} value={v.classification_rationale} onChange={(e) => set("classification_rationale", e.target.value)} /></Field>
      <Field label="Limitations"><textarea className="textarea" rows={2} value={v.limitations} onChange={(e) => set("limitations", e.target.value)} /></Field>
      <div>
        <span className="label">Documentation checklist</span>
        <div className="grid gap-1 sm:grid-cols-2">
          {facets.documentation_artifacts.map((a: string) => (
            <label key={a} className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={!!v.documentation_checklist?.[a]}
              onChange={(e) => set("documentation_checklist", { ...v.documentation_checklist, [a]: e.target.checked })} />{a}</label>))}
        </div>
        <div className="mt-2 w-48"><Field label="Documentation reviewed on"><input className="input" type="date" value={v.documentation_reviewed_on ?? ""} onChange={(e) => set("documentation_reviewed_on", e.target.value)} /></Field></div>
      </div>
      <ErrorBox error={err} />
      {!model && <Empty>New models start as Pending Approval. Approval and validation dates come from the validation workflow.</Empty>}
    </Modal>
  );
}
