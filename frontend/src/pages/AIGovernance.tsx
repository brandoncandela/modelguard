import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { ActionButton, Badge, Drawer, Empty, ErrorBox, Field, KV, Kpi, Modal, Notice, Panel, RiskBadge, Spinner,
  StatusBadge, Tabs } from "../components/ui";
import { COLORS, Plot } from "../components/charts/Plot";
import { date, dateTime, dec, metricLabel, num, pct } from "../lib/format";

const CLS_TONE: Record<string, any> = { "Prohibited practice (Art. 5)": "red", "High-risk (Art. 6, Annex III)": "orange",
  "Transparency obligations (Art. 50)": "blue", "Minimal risk": "green", "Not assessed": "slate" };

export default function AIGovernance() {
  const { systemId } = useParams();
  const nav = useNavigate();
  const [template, setTemplate] = useState(false);
  const meta = useQuery({ queryKey: ["ai-meta"], queryFn: () => api("/ai/meta") });
  const list = useQuery({ queryKey: ["ai-systems"], queryFn: () => api("/ai/systems") });
  const systems = (list.data ?? []) as any[];
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    systems.forEach((s) => (c[s.eu_ai_act_class] = (c[s.eu_ai_act_class] ?? 0) + 1));
    return c;
  }, [systems]);
  return (
    <div className="space-y-4">
      <Notice>{meta.data?.disclaimer ?? "Internal readiness self-assessment."} Annex III high-risk obligations apply from 2 December 2027 under Regulation (EU) 2026/1744. Generative AI is outside the scope of SR 26-2 and is governed here under internal policy AI-POL-002.</Notice>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="AI systems" value={systems.length} note={`${systems.filter((s) => ["Production", "Pilot"].includes(s.deployment_status)).length} deployed or in pilot`} />
        <Kpi label="Awaiting approval" value={systems.filter((s) => ["Draft", "Under Review"].includes(s.approval_status)).length} />
        <Kpi label="High-risk" value={counts["High-risk (Art. 6, Annex III)"] ?? 0} note="approved classification" tone={(counts["High-risk (Art. 6, Annex III)"] ?? 0) ? "warn" : undefined} />
        <Kpi label="Transparency" value={counts["Transparency obligations (Art. 50)"] ?? 0} note="Article 50" />
        <Kpi label="Prohibited (blocked)" value={counts["Prohibited practice (Art. 5)"] ?? 0} tone={(counts["Prohibited practice (Art. 5)"] ?? 0) ? "bad" : undefined} />
        <Kpi label="Not yet assessed" value={counts["Not assessed"] ?? 0} note="no approved assessment" />
      </div>
      <Panel title="AI system inventory" bodyClass="" actions={<button className="btn-ghost h-7" onClick={() => setTemplate(true)}>Assessment template</button>}>
        {list.isLoading ? <Spinner /> : (
          <DataTable rowKey={(s: any) => s.system_id} rows={systems} onRowClick={(s: any) => nav(`/ai/${s.system_id}`)}
            columns={[
              { key: "id", header: "System", sort: (s: any) => s.system_id, render: (s: any) => <div className="min-w-[220px]"><div className="font-medium">{s.system_id} {s.name}</div><div className="text-[11.5px] text-muted">{s.business_unit}</div></div> },
              { key: "tech", header: "Technique", render: (s: any) => <span className="text-[12px]">{s.ai_technique}</span> },
              { key: "m", header: "Inventory model", render: (s: any) => s.linked_model ? <span className="whitespace-nowrap text-[12px]">{s.linked_model.model_id}</span> : <span className="text-muted">–</span> },
              { key: "tier", header: "Tier", render: (s: any) => <RiskBadge r={s.internal_risk_tier} /> },
              { key: "cls", header: "EU AI Act (readiness view)", render: (s: any) => (
                <div><Badge tone={CLS_TONE[s.eu_ai_act_class] ?? "slate"}>{s.eu_ai_act_class}</Badge>
                  {s.latest_assessment && s.latest_assessment.status !== "Approved" && <div className="mt-0.5 text-[11.5px] text-muted">{s.latest_assessment.status}: {s.latest_assessment.derived_classification}</div>}</div>) },
              { key: "dep", header: "Deployment", render: (s: any) => <StatusBadge s={s.deployment_status} /> },
              { key: "appr", header: "Approval", render: (s: any) => <StatusBadge s={s.approval_status} /> },
              { key: "ev", header: "Latest evaluation", render: (s: any) => s.latest_evaluation ? <span className="whitespace-nowrap"><StatusBadge s={s.latest_evaluation.passed ? "Pass" : "Fail"} /> <span className="text-[11.5px] text-muted">{s.latest_evaluation.model_version}</span></span> : <span className="text-muted">–</span> },
              { key: "b", header: "Bias test", render: (s: any) => <StatusBadge s={s.bias_testing_status} /> },
            ]} />)}
      </Panel>
      {systemId && meta.data && <SystemDrawer id={systemId} meta={meta.data} onClose={() => nav("/ai")} />}
      {template && <TemplateModal onClose={() => setTemplate(false)} />}
    </div>
  );
}

function SystemDrawer({ id, meta, onClose }: { id: string; meta: any; onClose: () => void }) {
  const qc = useQueryClient();
  const { can, user } = useAuth();
  const [tab, setTab] = useState("overview");
  const q = useQuery({ queryKey: ["ai-system", id], queryFn: () => api(`/ai/systems/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["ai-system", id] }); qc.invalidateQueries({ queryKey: ["ai-systems"] }); };
  const s = q.data;
  if (q.isLoading || !s) return <Drawer open onClose={onClose} title={id}><Spinner /></Drawer>;
  const reviewer = ["compliance_reviewer", "admin"].includes(user!.role) && ![s.model_owner.id, s.system_owner.id].includes(user!.id);
  return (
    <Drawer open onClose={onClose} width="max-w-5xl" title={
      <div><div className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold">{s.system_id} {s.name}</span>
        <Badge tone={CLS_TONE[s.eu_ai_act_class] ?? "slate"}>{s.eu_ai_act_class}</Badge><StatusBadge s={s.approval_status} /></div>
        <div className="text-[12.5px] text-muted">{s.use_case}</div></div>}>
      <div className="space-y-4 p-5">
        {reviewer && (
          <div className="flex flex-wrap gap-2">
            {["Approved", "Approved with Conditions", "Rejected", "Retired"].map((d) => (
              <ActionButton key={d} label={d === "Approved" ? "Approve system" : d === "Rejected" ? "Reject" : d === "Retired" ? "Retire" : "Approve with conditions"}
                tone={d === "Rejected" ? "danger" : d.startsWith("Approved") ? "primary" : "ghost"} title={`AI Governance Committee decision: ${d}`}
                commentLabel={d === "Approved with Conditions" ? "Conditions" : "Notes"} minComment={d === "Approved with Conditions" ? 20 : 0}
                onRun={(c) => api(`/ai/systems/${id}/decision`, { body: { decision: d, conditions: c } }).then(refresh)} />))}
          </div>)}
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "overview", label: "Overview" }, { id: "assessment", label: "EU AI Act readiness" },
          { id: "evaluation", label: `LLM evaluation (${s.evaluations.length})` }, { id: "bias", label: "Bias testing" }]} />
        {tab === "overview" && (
          <div className="space-y-4">
            <KV items={[["Model owner", s.model_owner.full_name], ["System owner", s.system_owner.full_name], ["Business unit", s.business_unit],
              ["Technique", s.ai_technique], ["Provider", s.provider], ["Deployment", <StatusBadge s={s.deployment_status} />],
              ["Inventory model", s.linked_model ? <Link className="text-accent hover:underline" to={`/inventory/${s.linked_model.model_id}`}>{s.linked_model.model_id}</Link> : "Not a scored model"],
              ["Internal risk tier", <RiskBadge r={s.internal_risk_tier} />], ["Affects natural persons", s.affects_natural_persons ? "Yes" : "No"],
              ["Interacts with the public", s.interacts_with_public ? "Yes" : "No"], ["Approved on", date(s.approved_on)], ["Next review", date(s.next_review_date)]]} />
            {[["Business justification", s.business_justification], ["Intended use", s.intended_use], ["Prohibited use", s.prohibited_use],
              ["Data sources", s.data_sources.join(", ")], ["Human oversight", `${s.human_oversight}. ${s.oversight_description}`],
              ["Explainability", `${s.explainability_rating}. ${s.explainability_notes}`], ["Performance monitoring", s.performance_monitoring],
              ["Hallucination evaluation", s.hallucination_evaluation || "Not applicable"], ["Bias testing", `${s.bias_testing_status}. ${s.bias_testing_summary}`],
              ["Limitations", s.limitations]].map(([k, v]) => <div key={k}><div className="kv-k mb-0.5">{k}</div><div className="text-[13px] leading-5">{v || "–"}</div></div>)}
          </div>)}
        {tab === "assessment" && <AssessmentTab system={s} meta={meta} onChange={refresh} />}
        {tab === "evaluation" && <EvaluationTab system={s} canRun={can("ai:eval_run")} onChange={refresh} />}
        {tab === "bias" && <BiasTab system={s} canRun={can("ai:bias_test")} onChange={refresh} />}
      </div>
    </Drawer>
  );
}

function AssessmentTab({ system, meta, onChange }: { system: any; meta: any; onChange: () => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [sel, setSel] = useState<string | undefined>(system.assessments[0]?.assessment_id);
  const a = useQuery({ queryKey: ["assessment", sel], queryFn: () => api(`/ai/assessments/${sel}`), enabled: !!sel });
  const [answers, setAnswers] = useState<Record<number, { answer: string; evidence_note: string }>>({});
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    if (a.data) setAnswers(Object.fromEntries(a.data.questions.map((q: any) => [q.question_id, { answer: q.answer ?? "", evidence_note: q.evidence_note ?? "" }])));
  }, [a.data]);
  const reload = () => { qc.invalidateQueries({ queryKey: ["assessment", sel] }); onChange(); };
  const start = useMutation({ mutationFn: () => api(`/ai/systems/${system.system_id}/assessments`, { method: "POST" }),
    onSuccess: (r) => { setSel(r.assessment_id); onChange(); } });
  const save = async () => {
    setErr(null);
    const items = Object.entries(answers).filter(([, v]) => v.answer).map(([k, v]) => ({ question_id: Number(k), ...v }));
    try { await api(`/ai/assessments/${sel}/responses`, { method: "PUT", body: { items } }); reload(); } catch (e) { setErr(e); }
  };
  const submit = async () => { setErr(null); try { await save(); await api(`/ai/assessments/${sel}/submit`, { method: "POST" }); reload(); } catch (e) { setErr(e); } };
  if (!sel) return (
    <div className="space-y-3"><Empty>No assessment yet.</Empty>
      {system.can_edit && can("ai:assess") && <button className="btn-primary" onClick={() => start.mutate()}>Start EU AI Act readiness assessment</button>}
      <ErrorBox error={start.error} /></div>);
  if (a.isLoading || !a.data) return <Spinner />;
  const d = a.data;
  const byCat: Record<string, any[]> = {};
  d.questions.forEach((q: any) => (byCat[q.category] ??= []).push(q));
  const canStartNew = system.can_edit && can("ai:assess") && !system.assessments.some((x: any) => ["Draft", "Submitted", "Returned"].includes(x.status));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Assessment"><select className="input w-64" value={sel} onChange={(e) => setSel(e.target.value)}>
          {system.assessments.map((x: any) => <option key={x.assessment_id} value={x.assessment_id}>{x.assessment_id} · {x.status}</option>)}</select></Field>
        {canStartNew && <button className="btn-ghost" onClick={() => start.mutate()}>New assessment</button>}
        {d.can_edit && <><button className="btn-ghost" onClick={save}>Save answers</button><button className="btn-primary" onClick={submit}>Submit for review</button></>}
        {d.can_review && <>
          <ActionButton label="Approve assessment" tone="primary" commentLabel="Comments" onRun={(c) => api(`/ai/assessments/${sel}/review`, { body: { decision: "Approved", comments: c } }).then(reload)} />
          <ActionButton label="Return" commentLabel="What must change" minComment={10} onRun={(c) => api(`/ai/assessments/${sel}/review`, { body: { decision: "Returned", comments: c } }).then(reload)} />
        </>}
      </div>
      <ErrorBox error={err} />
      <div className="grid gap-3 md:grid-cols-[260px_1fr]">
        <Panel title="Result" bodyClass="space-y-3 p-3">
          <div><div className="kv-k">Derived classification</div><Badge tone={CLS_TONE[d.derived_classification] ?? "slate"}>{d.derived_classification}</Badge></div>
          <div><div className="kv-k">Status</div><StatusBadge s={d.status} /> <span className="text-[11.5px] text-muted">{d.assessor.full_name}{d.reviewer ? ` → ${d.reviewer.full_name}` : ""}</span></div>
          <div><div className="kv-k">Overall readiness</div><div className="text-[20px] font-semibold">{d.overall_score ?? "–"}{d.overall_score !== null ? "%" : ""}</div></div>
          <ul className="space-y-1">{Object.entries(d.category_scores).map(([c, v]: any) => (
            <li key={c}><div className="flex justify-between text-[12px]"><span>{c}</span><span>{v}%</span></div>
              <div className="h-1.5 rounded bg-sunken"><div className={`h-1.5 rounded ${v >= 80 ? "bg-ok" : v >= 50 ? "bg-warn" : "bg-bad"}`} style={{ width: `${v}%` }} /></div></li>))}</ul>
          {d.review_comments && <div><div className="kv-k">Reviewer comments</div><div className="text-[12.5px]">{d.review_comments}</div></div>}
          <p className="text-[11px] text-muted">{d.disclaimer} Template v{d.template.version}.</p>
        </Panel>
        <div className="space-y-3">
          {meta.categories.map((cat: string) => byCat[cat] && (
            <Panel key={cat} title={cat} bodyClass="divide-y divide-line">
              {byCat[cat].map((q: any) => (
                <div key={q.question_id} className="grid gap-2 px-4 py-2.5 lg:grid-cols-[1fr_140px]">
                  <div>
                    <div className="text-[12.5px]"><span className="font-medium">{q.code}</span> {q.text}</div>
                    <div className="text-[11.5px] text-muted">{q.reference}{q.classification_trigger ? ` · Yes sets: ${q.classification_trigger}` : ""}</div>
                    {(d.can_edit || answers[q.question_id]?.evidence_note) && (
                      <input className="input mt-1" disabled={!d.can_edit} placeholder="Evidence or note" value={answers[q.question_id]?.evidence_note ?? ""}
                        onChange={(e) => setAnswers((s) => ({ ...s, [q.question_id]: { ...s[q.question_id], evidence_note: e.target.value } }))} />)}
                  </div>
                  <select className="input" disabled={!d.can_edit} aria-label={`${q.code} answer`} value={answers[q.question_id]?.answer ?? ""}
                    onChange={(e) => setAnswers((s) => ({ ...s, [q.question_id]: { ...s[q.question_id], answer: e.target.value } }))}>
                    <option value="">Unanswered</option>{meta.answers.map((x: string) => <option key={x}>{x}</option>)}</select>
                </div>))}
            </Panel>))}
          {d.gaps.length > 0 && (
            <Panel title={`Gaps (${d.gaps.length})`} bodyClass="">
              <DataTable rowKey={(g: any) => g.code} rows={d.gaps} columns={[{ key: "c", header: "Question", render: (g: any) => <span className="font-medium">{g.code}</span> },
                { key: "a", header: "Answer", render: (g: any) => <StatusBadge s={g.answer === "No" ? "Gap" : "Partial"} /> },
                { key: "t", header: "Requirement", render: (g: any) => <span className="text-[12.5px]">{g.question}</span> }, { key: "r", header: "Reference", render: (g: any) => g.reference }]} />
            </Panel>)}
        </div>
      </div>
    </div>
  );
}

function EvaluationTab({ system, canRun, onChange }: { system: any; canRun: boolean; onChange: () => void }) {
  const [version, setVersion] = useState(system.eval_versions[0] ?? "");
  const [runId, setRunId] = useState<string | undefined>(system.evaluations[0]?.run_id);
  const run = useQuery({ queryKey: ["eval", runId], queryFn: () => api(`/ai/eval/runs/${runId}`), enabled: !!runId });
  const exec = useMutation({ mutationFn: () => api("/ai/eval/runs", { body: { system_id: system.system_id, model_version: version } }),
    onSuccess: (r) => { setRunId(r.run_id); onChange(); } });
  if (!system.eval_versions.length) return <Empty>No evaluation cases for this system. The deterministic suite covers the two generative systems linked to the inventory (AI-001 and AI-002).</Empty>;
  const metricsOrder = ["factual_accuracy", "unsupported_claim_rate", "hallucination_rate", "policy_compliance", "response_consistency", "override_rate"];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Run"><select className="input w-72" value={runId} onChange={(e) => setRunId(e.target.value)}>
          {system.evaluations.map((e: any) => <option key={e.run_id} value={e.run_id}>{e.run_id} · {e.model_version} · {e.passed ? "Pass" : "Fail"} · {dateTime(e.run_at)}</option>)}</select></Field>
        {canRun && <>
          <Field label="Model version"><select className="input w-40" value={version} onChange={(e) => setVersion(e.target.value)}>
            {system.eval_versions.map((v: string) => <option key={v}>{v}</option>)}</select></Field>
          <button className="btn-primary" disabled={exec.isPending} onClick={() => exec.mutate()}>Run suite</button></>}
      </div>
      <ErrorBox error={exec.error} />
      {run.data && (<>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          {metricsOrder.map((k) => {
            const t = run.data.threshold_results.find((x: any) => x.metric === k);
            return (
              <div key={k} className={`panel px-3 py-2 ${t?.status === "Breach" ? "border-bad/40" : t?.status === "Warning" ? "border-warn/40" : ""}`}>
                <div className="text-xxs font-medium uppercase tracking-wide text-muted">{metricLabel[k]}</div>
                <div className="text-[18px] font-semibold">{pct(run.data.metrics[k])}</div>
                <div className="text-[11px] text-muted">{t ? <><StatusBadge s={t.status} /> {t.direction === "min" ? "min" : "max"} {pct(t.breach_limit)}</> : "no threshold"}</div>
              </div>);
          })}
        </div>
        <Panel title={`${run.data.run_id} · ${run.data.model_version} · ${run.data.case_count} cases`} bodyClass="" actions={<StatusBadge s={run.data.passed ? "Pass" : "Fail"} />}>
          <DataTable rowKey={(r: any) => r.case_id} rows={run.data.results} columns={[
            { key: "c", header: "Case", render: (r: any) => <div><div className="font-medium whitespace-nowrap">{r.case_id}</div><div className="text-[11.5px] text-muted">{r.category}</div></div> },
            { key: "p", header: "Prompt and response", render: (r: any) => <div className="min-w-[320px] max-w-[520px]"><div className="text-[12px] text-muted">{r.prompt}</div><div className="mt-1 text-[12.5px]">{r.response}</div></div> },
            { key: "f", header: "Facts", align: "right", render: (r: any) => (r.facts_expected ? `${r.facts_found}/${r.facts_expected}` : "–") },
            { key: "flags", header: "Flags", render: (r: any) => (
              <div className="flex max-w-[260px] flex-wrap gap-1">
                {r.hallucinated_references.map((h: string) => <Badge key={h} tone="red">Fabricated: {h}</Badge>)}
                {r.unsupported_claims.length > 0 && <Badge tone="amber" title={r.unsupported_claims.join("\n")}>{r.unsupported_claims.length} unsupported claim{r.unsupported_claims.length > 1 ? "s" : ""}</Badge>}
                {r.policy_violations.map((p: string) => <Badge key={p} tone="red">{p.replace(/_/g, " ")}</Badge>)}
                {!r.behavior_correct && <Badge tone="red">Wrong behaviour</Badge>}
                {r.normalized_answer && <Badge tone="slate">Answer: {r.normalized_answer}</Badge>}
              </div>) },
            { key: "rev", header: "Reviewer", render: (r: any) => <Badge tone={r.reviewer_decision === "Overridden" ? "red" : r.reviewer_decision === "Edited" ? "amber" : "green"}>{r.reviewer_decision}</Badge> },
            { key: "res", header: "Result", render: (r: any) => <StatusBadge s={r.passed ? "Pass" : "Fail"} /> }]} />
        </Panel>
        <p className="text-[11.5px] text-muted">{run.data.disclaimer} Responses are recorded outputs scored by fixed rules; no model is called.</p>
      </>)}
    </div>
  );
}

function BiasTab({ system, canRun, onChange }: { system: any; canRun: boolean; onChange: () => void }) {
  const exec = useMutation({ mutationFn: () => api(`/ai/systems/${system.system_id}/bias-test`, { method: "POST" }), onSuccess: onChange });
  const t = system.bias_tests[0];
  return (
    <div className="space-y-4">
      {canRun && system.bias_testable && <button className="btn-primary" disabled={exec.isPending} onClick={() => exec.mutate()}>Run outcome disparity test</button>}
      <ErrorBox error={exec.error} />
      {!t ? <Empty>{system.bias_testable ? "No test run yet." : "Disparity testing runs for systems linked to the onboarding classifier (MDL-COR-010) or the ML detection model (MDL-SAD-007)."}</Empty> : (<>
        <KV cols={4} items={[["Result", <StatusBadge s={t.passed ? "Passed" : "Review required"} />], ["Periods", t.periods], ["Records", num(t.records)],
          ["Min impact / FPR ratio", `${dec(t.min_impact_ratio)} / ${dec(t.min_fpr_ratio)}`]]} />
        <Panel title={`Adverse outcome rate by ${t.attribute}`}>
          <Plot ariaLabel="Bar chart of adverse outcome and false positive rates by group" height={240} data={[
            { type: "bar", name: "Adverse outcome rate", x: t.groups.map((g: any) => g.group), y: t.groups.map((g: any) => g.adverse_rate), marker: { color: COLORS.accent } },
            { type: "bar", name: "False positive rate", x: t.groups.map((g: any) => g.group), y: t.groups.map((g: any) => g.false_positive_rate), marker: { color: COLORS.orange } }]}
            layout={{ barmode: "group", yaxis: { tickformat: ".1%", gridcolor: "#EEF2F7" } }} />
        </Panel>
        <Panel bodyClass="">
          <DataTable rowKey={(g: any) => g.group} rows={t.groups} columns={[
            { key: "g", header: "Group", render: (g: any) => <span className="font-medium">{g.group}</span> }, { key: "n", header: "Records", align: "right", render: (g: any) => num(g.n) },
            { key: "a", header: "Adverse rate", align: "right", render: (g: any) => pct(g.adverse_rate) }, { key: "b", header: "Base rate", align: "right", render: (g: any) => pct(g.base_rate) },
            { key: "ir", header: "Impact ratio", align: "right", render: (g: any) => dec(g.impact_ratio) }, { key: "ip", header: "p", align: "right", render: (g: any) => dec(g.impact_p_value) },
            { key: "fr", header: "FPR ratio", align: "right", render: (g: any) => dec(g.fpr_ratio) }, { key: "fp", header: "p", align: "right", render: (g: any) => dec(g.fpr_p_value) },
            { key: "t", header: "Tested", render: (g: any) => (g.tested ? "Yes" : <span className="text-muted">Under 100 records</span>) },
            { key: "f", header: "Flag", render: (g: any) => (g.flag ? <Badge tone="red">Review</Badge> : <span className="text-muted">–</span>) }]} />
        </Panel>
        <p className="text-[12px] text-muted">{t.method} Groups are flagged only when a ratio is below 0.80 and the difference is significant at 5%. The four-fifths heuristic is a screening convention, not a legal test. Nationality region is a synthetic attribute.</p>
      </>)}
    </div>
  );
}

function TemplateModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const t = useQuery({ queryKey: ["ai-template"], queryFn: () => api("/ai/templates/active") });
  const meta = useQuery({ queryKey: ["ai-meta"], queryFn: () => api("/ai/meta") });
  const [v, setV] = useState<any>({ code: "", category: "Transparency", text: "", reference: "", classification_trigger: "" });
  const add = useMutation({ mutationFn: () => api("/ai/templates/questions", { body: { ...v, classification_trigger: v.classification_trigger || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ai-template"] }); setV({ ...v, code: "", text: "", reference: "" }); } });
  const toggle = useMutation({ mutationFn: (q: any) => api(`/ai/templates/questions/${q.id}`, { method: "PATCH", body: { is_active: !q.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-template"] }) });
  const edit = can("ai:template_edit");
  return (
    <Modal open onClose={onClose} title={t.data ? `${t.data.name} v${t.data.version}` : "Assessment template"} footer={<button className="btn-ghost" onClick={onClose}>Close</button>}>
      {!t.data ? <Spinner /> : (<>
        <p className="text-[12px] text-muted">{t.data.framework}. Changes apply to new assessments; existing answers are kept.</p>
        <ul className="divide-y divide-line rounded-md border border-line">{t.data.questions.map((q: any) => (
          <li key={q.id} className={`flex items-start gap-2 px-3 py-2 ${q.is_active ? "" : "opacity-50"}`}>
            <span className="w-12 shrink-0 font-medium">{q.code}</span><span className="flex-1 text-[12px]">{q.text}<span className="block text-[11px] text-muted">{q.category} · {q.reference}</span></span>
            {edit && <button className="btn-ghost h-6 px-2 text-[11px]" onClick={() => toggle.mutate(q)}>{q.is_active ? "Deactivate" : "Activate"}</button>}
          </li>))}</ul>
        {edit && meta.data && (
          <div className="space-y-2 rounded-md border border-line p-3">
            <div className="font-medium">Add a question</div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Code" hint="e.g. TR-04"><input className="input" value={v.code} onChange={(e) => setV({ ...v, code: e.target.value.toUpperCase() })} /></Field>
              <Field label="Category"><select className="input" value={v.category} onChange={(e) => setV({ ...v, category: e.target.value })}>{meta.data.categories.map((c: string) => <option key={c}>{c}</option>)}</select></Field>
            </div>
            <Field label="Question"><textarea className="textarea" rows={2} value={v.text} onChange={(e) => setV({ ...v, text: e.target.value })} /></Field>
            <Field label="Reference"><input className="input" value={v.reference} onChange={(e) => setV({ ...v, reference: e.target.value })} /></Field>
            {v.category === "Risk classification" && <Field label="Classification when answered Yes"><select className="input" value={v.classification_trigger} onChange={(e) => setV({ ...v, classification_trigger: e.target.value })}>
              <option value="">None</option>{meta.data.classifications.slice(0, 3).map((c: string) => <option key={c}>{c}</option>)}</select></Field>}
            <ErrorBox error={add.error} />
            <button className="btn-primary" onClick={() => add.mutate()}>Add question</button>
          </div>)}
      </>)}
    </Modal>
  );
}
