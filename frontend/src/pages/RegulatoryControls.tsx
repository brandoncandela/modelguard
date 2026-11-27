import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { Badge, Drawer, ErrorBox, Field, KV, Notice, Panel, Spinner, StatusBadge, Tabs, Timeline } from "../components/ui";
import { date, dateTime } from "../lib/format";
import { EvidencePanel } from "./ValidationManagement";

const TYPE_TONE: Record<string, any> = { Regulation: "blue", "Supervisory guidance": "green", "Internal policy": "slate" };

export default function RegulatoryControls() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [tab, setTab] = useState("coverage");
  const [ctl, setCtl] = useState<string | null>(null);
  const [src, setSrc] = useState("");
  const cov = useQuery({ queryKey: ["reg-coverage"], queryFn: () => api("/regulatory/coverage") });
  const reqs = useQuery({ queryKey: ["reg-reqs"], queryFn: () => api("/regulatory/requirements") });
  const ctrls = useQuery({ queryKey: ["reg-controls"], queryFn: () => api("/regulatory/controls") });
  const sources = useQuery({ queryKey: ["reg-sources"], queryFn: () => api("/regulatory/sources") });
  const run = useMutation({ mutationFn: () => api("/regulatory/controls/test", { body: {} }), onSuccess: () => qc.invalidateQueries() });
  const c = cov.data;
  return (
    <div className="space-y-4">
      <Notice>{c?.disclaimer ?? ""} Sources were last checked against the published text on {date(sources.data?.items?.[0]?.last_reviewed_on)}.</Notice>
      {c && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {c.by_source.map((b: any) => (
            <button key={b.source} onClick={() => { setSrc(b.source); setTab("coverage"); }} className={`panel px-3 py-2.5 text-left hover:border-accent/40 ${src === b.source ? "border-accent" : ""}`}>
              <div className="flex items-center justify-between gap-2"><span className="font-medium">{b.source}</span><StatusBadge s={b.status} /></div>
              <div className="mt-1 text-[12px] text-muted">{b.total} requirement{b.total > 1 ? "s" : ""}</div>
              <div className="mt-1 flex flex-wrap gap-1">{["Covered", "Partially covered", "Gap", "No control mapped", "Historical reference"].filter((k) => b[k]).map((k) => <span key={k}><StatusBadge s={k} /> {b[k]}</span>)}</div>
            </button>))}
        </div>)}
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "coverage", label: "Requirement coverage" }, { id: "controls", label: `Controls (${c?.controls.total ?? ""})` }, { id: "sources", label: "Source library" }]} />
        <div className="ml-auto flex items-center gap-2 text-[12px] text-muted">
          {c && <span>{c.controls.tests_passing} of {c.controls.automated} automated tests passing</span>}
          {can("regulatory:test") && <button className="btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Testing" : "Run control tests"}</button>}
        </div>
      </div>
      <ErrorBox error={run.error} />
      {tab === "coverage" && (
        <Panel bodyClass="" title={src ? `Requirements: ${src}` : "All requirements"} actions={src ? <button className="btn-ghost h-7" onClick={() => setSrc("")}>Show all</button> : null}>
          {reqs.isLoading ? <Spinner /> : (
            <DataTable rowKey={(r: any) => r.requirement_id} rows={(reqs.data?.items ?? []).filter((r: any) => !src || r.source === src)}
              columns={[
                { key: "id", header: "Requirement", render: (r: any) => <div><div className="font-medium whitespace-nowrap">{r.requirement_id}</div><div className="text-[11.5px] text-muted">{r.source} · {r.section}</div></div> },
                { key: "t", header: "Type", render: (r: any) => <Badge tone={TYPE_TONE[r.obligation_type]}>{r.obligation_type}</Badge> },
                { key: "s", header: "Summary (paraphrased)", render: (r: any) => <div className="min-w-[320px] text-[12.5px]">{r.summary}</div> },
                { key: "c", header: "Controls", render: (r: any) => <div className="flex flex-wrap gap-1">{r.controls.map((x: string) => (
                  <button key={x} className="text-accent hover:underline" onClick={() => setCtl(x)}>{x}</button>))}</div> },
                { key: "cov", header: "Coverage", sort: (r: any) => r.coverage, render: (r: any) => <StatusBadge s={r.coverage} /> },
              ]} />)}
        </Panel>)}
      {tab === "controls" && (
        <Panel bodyClass="">
          {ctrls.isLoading ? <Spinner /> : (
            <DataTable rowKey={(x: any) => x.control_id} rows={ctrls.data.items} onRowClick={(x: any) => setCtl(x.control_id)}
              columns={[
                { key: "id", header: "Control", render: (x: any) => <div className="min-w-[220px]"><div className="font-medium">{x.control_id} {x.name}</div><div className="text-[11.5px] text-muted">{x.control_type} · {x.frequency}</div></div> },
                { key: "o", header: "Owner", render: (x: any) => x.owner.full_name },
                { key: "s", header: "Implementation", render: (x: any) => <StatusBadge s={x.implementation_status} /> },
                { key: "t", header: "Latest test", render: (x: any) => x.latest_test ? <div><StatusBadge s={x.latest_test.result} /> <span className="text-[11.5px] text-muted">{x.latest_test.exceptions} exc. / {x.latest_test.population}</span></div> : <span className="text-[12px] text-muted">Manual</span> },
                { key: "r", header: "Requirements", render: (x: any) => <span className="text-[12px]">{x.requirements.map((r: any) => r.requirement_id).join(", ")}</span> },
                { key: "rev", header: "Last review", render: (x: any) => date(x.last_reviewed_on) },
                { key: "g", header: "Gaps", render: (x: any) => <span className="text-[12px] text-muted">{x.identified_gaps || "–"}</span> },
              ]} />)}
        </Panel>)}
      {tab === "sources" && (
        <div className="grid gap-3 lg:grid-cols-2">
          {(sources.data?.items ?? []).map((s: any) => (
            <Panel key={s.source_id} title={<span className="flex items-center gap-2">{s.short_name}<Badge tone={TYPE_TONE[s.source_type]}>{s.source_type}</Badge><StatusBadge s={s.status} /></span>}>
              <div className="space-y-2 text-[12.5px]">
                <div className="font-medium">{s.title}</div>
                <KV cols={2} items={[["Issuer", s.issuer], ["Citation", s.citation], ["Published", date(s.published_on)], ["Last reviewed", date(s.last_reviewed_on)],
                  ...(s.superseded_by ? [["Replaced by", `${s.superseded_by} on ${date(s.superseded_on)}`] as [string, string]] : [])]} />
                {s.applicability && <p>{s.applicability}</p>}
                {s.notes && <p className="text-muted">{s.notes}</p>}
                {s.url && <a className="text-accent hover:underline" href={s.url} target="_blank" rel="noopener noreferrer">{s.url}</a>}
              </div>
            </Panel>))}
        </div>)}
      {ctl && <ControlDrawer id={ctl} onClose={() => setCtl(null)} />}
    </div>
  );
}

function ControlDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["control", id], queryFn: () => api(`/regulatory/controls/${id}`) });
  const [edit, setEdit] = useState<any>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["control", id] }); qc.invalidateQueries({ queryKey: ["reg-controls"] }); qc.invalidateQueries({ queryKey: ["reg-coverage"] }); qc.invalidateQueries({ queryKey: ["reg-reqs"] }); };
  const save = useMutation({ mutationFn: () => api(`/regulatory/controls/${id}`, { method: "PATCH", body: edit }), onSuccess: () => { setEdit(null); refresh(); } });
  const test = useMutation({ mutationFn: () => api("/regulatory/controls/test", { body: { control_id: id } }), onSuccess: refresh });
  const x = q.data;
  return (
    <Drawer open onClose={onClose} title={x ? <div><div className="flex items-center gap-2"><span className="text-[15px] font-semibold">{x.control_id} {x.name}</span><StatusBadge s={x.implementation_status} /></div>
      <div className="text-[12.5px] text-muted">{x.description}</div></div> : id}>
      {!x ? <Spinner /> : (
        <div className="space-y-4 p-5">
          <div className="flex gap-2">
            {can("regulatory:edit") && !edit && <button className="btn-ghost" onClick={() => setEdit({ implementation_status: x.implementation_status, identified_gaps: x.identified_gaps,
              remediation_actions: x.remediation_actions, last_reviewed_on: x.last_reviewed_on, next_review_on: x.next_review_on })}>Edit</button>}
            {can("regulatory:test") && x.automated_test && <button className="btn-ghost" disabled={test.isPending} onClick={() => test.mutate()}>Run this test</button>}
          </div>
          {edit ? (
            <Panel title="Update control" actions={<><button className="btn-ghost h-7" onClick={() => setEdit(null)}>Cancel</button><button className="btn-primary h-7" onClick={() => save.mutate()}>Save</button></>}>
              <div className="space-y-3">
                <Field label="Implementation status"><select className="input" value={edit.implementation_status} onChange={(e) => setEdit({ ...edit, implementation_status: e.target.value })}>
                  {["Implemented", "Partially implemented", "Not implemented", "Planned"].map((s) => <option key={s}>{s}</option>)}</select></Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Last reviewed"><input className="input" type="date" value={edit.last_reviewed_on ?? ""} onChange={(e) => setEdit({ ...edit, last_reviewed_on: e.target.value })} /></Field>
                  <Field label="Next review"><input className="input" type="date" value={edit.next_review_on ?? ""} onChange={(e) => setEdit({ ...edit, next_review_on: e.target.value })} /></Field>
                </div>
                <Field label="Identified gaps"><textarea className="textarea" rows={2} value={edit.identified_gaps} onChange={(e) => setEdit({ ...edit, identified_gaps: e.target.value })} /></Field>
                <Field label="Remediation actions"><textarea className="textarea" rows={2} value={edit.remediation_actions} onChange={(e) => setEdit({ ...edit, remediation_actions: e.target.value })} /></Field>
                <ErrorBox error={save.error} />
              </div>
            </Panel>) : (
            <KV cols={2} items={[["Owner", `${x.owner.full_name}, ${x.owner.title}`], ["Type / frequency", `${x.control_type} · ${x.frequency}`],
              ["Evidence requirement", x.evidence_requirement], ["Documentation", x.documentation_refs.join(", ")], ["Last reviewed", date(x.last_reviewed_on)],
              ["Next review", date(x.next_review_on)], ["Identified gaps", x.identified_gaps || "None"], ["Remediation actions", x.remediation_actions || "None"]]} />)}
          <ErrorBox error={test.error} />
          <Panel title="Mapped requirements" bodyClass="">
            <DataTable rowKey={(r: any) => r.requirement_id} rows={x.requirements} columns={[{ key: "id", header: "Requirement", render: (r: any) => <span className="font-medium whitespace-nowrap">{r.requirement_id}</span> },
              { key: "s", header: "Source", render: (r: any) => <span>{r.source} <StatusBadge s={r.source_status} /></span> }, { key: "sec", header: "Section", render: (r: any) => r.section },
              { key: "t", header: "Type", render: (r: any) => <Badge tone={TYPE_TONE[r.obligation_type]}>{r.obligation_type}</Badge> }]} />
          </Panel>
          <Panel title={`Mapped models (${x.models.length})`}><div className="flex flex-wrap gap-1.5">{x.models.map((m: any) => <Link key={m.model_id} to={`/inventory/${m.model_id}`} className="rounded border border-line px-2 py-0.5 text-[12px] hover:border-accent">{m.model_id}</Link>)}
            {!x.models.length && <span className="text-muted">Applies to AI systems rather than inventory models.</span>}</div></Panel>
          {x.automated_test && (
            <Panel title="Automated test history">
              <Timeline items={x.test_history.map((t: any) => ({ when: dateTime(t.run_at), who: t.run_by, title: <span><StatusBadge s={t.result} /> {t.exceptions} exception{t.exceptions === 1 ? "" : "s"} in {t.population}</span>,
                body: <><div className="text-muted">{t.summary}</div>{t.exception_items.length > 0 && <ul className="mt-1 list-disc pl-5">{t.exception_items.slice(0, 8).map((e: any, i: number) => <li key={i}><b>{e.item}</b>: {e.detail}</li>)}</ul>}</> }))} />
            </Panel>)}
          <EvidencePanel items={x.evidence} canAdd={can("regulatory:edit")} uploadPath={`/regulatory/controls/${id}/evidence`} onDone={refresh} />
        </div>)}
    </Drawer>
  );
}
