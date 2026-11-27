import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { DataTable } from "../components/ui/DataTable";
import { ActionButton, Badge, Drawer, Dot, Empty, ErrorBox, Field, Notice, Panel, SeverityBadge, Spinner,
  StatusBadge, Tabs } from "../components/ui";
import { COLORS, Plot, periodAxis, refBand } from "../components/charts/Plot";
import { dateTime, dec, fmtMetric, metricLabel, num } from "../lib/format";

const TILE_ORDER = ["precision", "recall", "f1", "false_positive_rate", "alert_conversion_rate", "override_rate", "psi",
  "max_feature_psi", "dq_exception_rate"];

export default function PerformanceMonitoring() {
  const { modelId } = useParams();
  const nav = useNavigate();
  const { can } = useAuth();
  const sum = useQuery({ queryKey: ["mon-summary"], queryFn: () => api("/monitoring/summary") });
  const [method, setMethod] = useState(false);
  const models = (sum.data?.models ?? []) as any[];
  const selected = modelId ?? models.find((m) => m.monitored_via === "scored_records")?.model_id;
  useEffect(() => {
    if (!modelId && selected) nav(`/monitoring/${selected}`, { replace: true });
  }, [modelId, selected, nav]);
  if (sum.isLoading) return <Spinner />;
  if (sum.error) return <ErrorBox error={sum.error} />;
  const row = models.find((m) => m.model_id === selected);
  return (
    <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
      <div className="space-y-4">
        <Panel title="Models" bodyClass="p-1" actions={<button className="btn-ghost h-7 px-2" onClick={() => setMethod(true)}>Methodology</button>}>
          <ul>
            {models.map((m) => {
              const sev = m.worst_open_severity;
              const tone = m.overall_status === "Breach" ? "red" : m.overall_status === "Warning" ? "amber" : m.overall_status ? "green" : "slate";
              return (
                <li key={m.model_id}>
                  <button onClick={() => m.monitored_via === "scored_records" ? nav(`/monitoring/${m.model_id}`) : nav(m.monitored_via === "llm_evaluation" ? "/ai" : "/inventory")}
                    className={`flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left ${m.model_id === selected ? "bg-accent-soft" : "hover:bg-sunken"}`}>
                    <span className="mt-1.5"><Dot tone={tone as any} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2"><span className="font-medium whitespace-nowrap">{m.model_id}</span>
                        {sev && <SeverityBadge s={sev} />}</span>
                      <span className="block truncate text-[12px] text-muted">{m.name}</span>
                      <span className="block text-[11.5px] text-muted">
                        {m.monitored_via === "scored_records" ? `${m.latest_period} · ${m.overall_status} · ${m.monitoring_frequency}` : "Monitored through the LLM evaluation suite"}
                      </span>
                    </span>
                  </button>
                </li>);
            })}
          </ul>
        </Panel>
        {can("monitoring:simulate") && <SimulationPanel periods={sum.data.periods} />}
        <PeriodsPanel periods={sum.data.periods} reference={sum.data.reference_periods} />
      </div>
      <div className="min-w-0">{row ? <ModelMonitoring key={row.model_id} row={row} /> : <Empty>Select a model.</Empty>}</div>
      <MethodologyDrawer open={method} onClose={() => setMethod(false)} />
    </div>
  );
}

function PeriodsPanel({ periods, reference }: { periods: any[]; reference: string[] }) {
  return (
    <Panel title="Synthetic periods" bodyClass="p-3">
      <div className="flex flex-wrap gap-1">
        {periods.map((p) => (
          <span key={p.period} title={`${p.scenario}, drift intensity ${p.drift_intensity}`}
            className={`rounded border px-1.5 py-0.5 text-[11px] ${p.is_reference ? "border-line bg-sunken text-muted" : p.drift_intensity > 0 ? "border-warn/30 bg-warn/10 text-warn" : "border-line"} ${p.source === "simulation" ? "ring-1 ring-accent/40" : ""}`}>
            {p.period}{p.drift_intensity > 0 ? ` · ${p.drift_intensity}` : ""}
          </span>))}
      </div>
      <p className="mt-2 text-[11.5px] text-muted">Grey: reference window ({reference[0]} to {reference[reference.length - 1]}). Amber: drift scenario with intensity. Outlined: simulated in the app.</p>
    </Panel>
  );
}

function SimulationPanel({ periods }: { periods: any[] }) {
  const qc = useQueryClient();
  const [scenario, setScenario] = useState("severe");
  const [result, setResult] = useState<any>(null);
  const sim = useMutation({ mutationFn: () => api("/monitoring/simulate", { body: { scenario } }),
    onSuccess: (r) => { setResult(r); qc.invalidateQueries(); } });
  const reset = useMutation({ mutationFn: () => api("/monitoring/simulate", { method: "DELETE" }),
    onSuccess: () => { setResult(null); qc.invalidateQueries(); } });
  const simulated = periods.filter((p) => p.source === "simulation").length;
  return (
    <Panel title="Drift scenario" bodyClass="space-y-2 p-3">
      <p className="text-[12px] text-muted">Generate the next month with the chosen drift, score it with every model and run monitoring.</p>
      <div className="flex gap-2">
        <select className="input" value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Drift scenario">
          <option value="none">No drift</option><option value="moderate">Moderate drift</option><option value="severe">Severe drift</option>
        </select>
        <button className="btn-primary shrink-0" disabled={sim.isPending} onClick={() => sim.mutate()}>{sim.isPending ? "Simulating" : "Simulate"}</button>
      </div>
      {simulated > 0 && <button className="btn-ghost w-full justify-center" disabled={reset.isPending} onClick={() => reset.mutate()}>Remove {simulated} simulated period{simulated > 1 ? "s" : ""}</button>}
      <ErrorBox error={sim.error ?? reset.error} />
      {result && (
        <div className="rounded-md border border-line bg-sunken p-2 text-[12px]">
          <div className="font-medium">{result.period} simulated ({result.scenario}) in {result.seconds}s</div>
          <div className="text-muted">{num(result.records.transactions)} transactions, {num(result.records.alerts)} alerts, {result.monitoring_runs} monitoring runs</div>
          <div className="mt-1 flex flex-wrap gap-1">{Object.entries(result.breaches).map(([s, n]) => <span key={s}><SeverityBadge s={s} /> {String(n)}</span>)}
            {!Object.keys(result.breaches).length && <span className="text-ok">No breaches</span>}</div>
          {result.models_in_breach.length > 0 && <div className="mt-1 text-muted">In breach: {result.models_in_breach.join(", ")}</div>}
        </div>)}
    </Panel>
  );
}

function ModelMonitoring({ row }: { row: any }) {
  const id = row.model_id;
  const [tab, setTab] = useState("performance");
  const series = useQuery({ queryKey: ["series", id], queryFn: () => api(`/monitoring/models/${id}/series`) });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api(`/monitoring/models/${id}/runs`) });
  const latestRun = (runs.data ?? []).find((r: any) => r.is_latest);
  const [period, setPeriod] = useState<string | null>(null);
  const runId = period ? (runs.data ?? []).find((r: any) => r.period === period && r.is_latest)?.run_id : latestRun?.run_id;
  const detail = useQuery({ queryKey: ["run", runId], queryFn: () => api(`/monitoring/runs/${runId}`), enabled: !!runId });
  const breaches = useQuery({ queryKey: ["breaches", id], queryFn: () => api("/monitoring/breaches", { query: { model_id: id, page_size: 200 } }) });

  return (
    <div className="space-y-4">
      <Panel bodyClass="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Link to={`/inventory/${id}`} className="text-[16px] font-semibold hover:underline">{id}</Link><StatusBadge s={detail.data?.overall_status ?? row.overall_status} />
              {detail.data?.scenario && detail.data.scenario !== "baseline" && <Badge tone="amber">{detail.data.scenario} drift</Badge>}</div>
            <div className="text-muted">{row.name}</div>
          </div>
          <div className="flex items-end gap-2">
            <Field label="Period"><select className="input w-36" value={period ?? latestRun?.period ?? ""} onChange={(e) => setPeriod(e.target.value)}>
              {[...new Set((runs.data ?? []).map((r: any) => r.period))].map((p: any) => <option key={p}>{p}</option>)}</select></Field>
            <RunButton modelId={id} period={period ?? latestRun?.period} />
          </div>
        </div>
        {detail.data && <div className="mt-2 text-[12px] text-muted">{num(detail.data.record_count)} records scored in {detail.data.period} · reference window {detail.data.reference} ({num(detail.data.reference_count)} records) · run {detail.data.run_id} by {detail.data.triggered_by}, {dateTime(detail.data.run_at)}</div>}
      </Panel>

      {detail.data && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-5">
          {TILE_ORDER.map((k) => detail.data.metrics.find((m: any) => m.metric === k)).filter(Boolean).map((m: any) => (
            <div key={m.metric} className={`panel px-3 py-2 ${m.status === "Breach" ? "border-bad/40" : m.status === "Warning" ? "border-warn/40" : ""}`}>
              <div className="flex items-center justify-between"><span className="text-xxs font-medium uppercase tracking-wide text-muted">{metricLabel[m.metric]}</span>
                {m.status !== "Within limits" && m.status !== "Not monitored" && <StatusBadge s={m.status} />}</div>
              <div className="mt-0.5 text-[18px] font-semibold">{fmtMetric(m.metric, m.value)}</div>
              <div className="text-[11px] text-muted">
                {m.warning_limit !== null ? `warn ${fmtMetric(m.metric, m.warning_limit)} · breach ${fmtMetric(m.metric, m.breach_limit)}` : "no threshold"}
                {m.denominator !== null && m.numerator !== null ? ` · ${num(m.numerator)}/${num(m.denominator)}` : ""}
              </div>
            </div>))}
        </div>)}

      <Tabs value={tab} onChange={setTab} tabs={[{ id: "performance", label: "Trends" }, { id: "drift", label: "Distribution and drift" },
        { id: "breaches", label: `Breaches (${(breaches.data?.items ?? []).filter((b: any) => b.status !== "Resolved").length} open)` },
        { id: "thresholds", label: "Thresholds" }, { id: "history", label: "Run history" }]} />

      {tab === "performance" && (series.isLoading ? <Spinner /> : <TrendCharts data={series.data} />)}
      {tab === "drift" && (detail.isLoading ? <Spinner /> : detail.data ? <DriftView run={detail.data} /> : <Empty>No run.</Empty>)}
      {tab === "breaches" && <BreachTable data={breaches.data?.items ?? []} modelId={id} />}
      {tab === "thresholds" && <ThresholdEditor modelId={id} />}
      {tab === "history" && (
        <Panel bodyClass=""><DataTable rowKey={(r: any) => r.run_id} rows={runs.data ?? []} onRowClick={(r: any) => setPeriod(r.period)}
          columns={[{ key: "run", header: "Run", render: (r: any) => <span className="font-medium whitespace-nowrap">{r.run_id}</span> },
            { key: "p", header: "Period", className: "whitespace-nowrap", render: (r: any) => r.period }, { key: "s", header: "Status", render: (r: any) => <StatusBadge s={r.overall_status} /> },
            { key: "sc", header: "Scenario", render: (r: any) => r.scenario }, { key: "n", header: "Records", align: "right", render: (r: any) => num(r.record_count) },
            { key: "l", header: "Latest", render: (r: any) => (r.is_latest ? "Yes" : <span className="text-muted">Superseded</span>) },
            { key: "t", header: "Run by", render: (r: any) => r.triggered_by }, { key: "at", header: "Run at", render: (r: any) => dateTime(r.run_at) }]} /></Panel>)}
    </div>
  );
}

function RunButton({ modelId, period }: { modelId: string; period?: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const m = useMutation({ mutationFn: () => api("/monitoring/runs", { body: { model_id: modelId, period } }), onSuccess: () => qc.invalidateQueries() });
  if (!can("monitoring:run")) return null;
  return <div><button className="btn-ghost" disabled={m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Running" : "Re-run monitoring"}</button>{m.error && <div className="mt-1 w-56"><ErrorBox error={m.error} /></div>}</div>;
}

function shading(periods: string[], ref: string[]) {
  return refBand(periods.filter((p) => ref.includes(p)).length);
}

function TrendCharts({ data }: { data: any }) {
  const s = data?.series ?? {};
  const ref = data?.reference_periods ?? [];
  const perfKeys = ["precision", "recall", "alert_conversion_rate", "override_rate"].filter((k) => s[k]);
  const x = (s.precision ?? s.recall ?? s.psi ?? [])?.map((p: any) => p.period) ?? [];
  const limitLines = (k: string, color: string) => {
    const last = s[k]?.slice(-1)[0];
    if (!last || last.warning_limit === null) return [];
    return [
      { type: "scatter", mode: "lines", name: `${metricLabel[k]} warning`, x, y: x.map(() => last.warning_limit), line: { color, dash: "dot", width: 1 }, hoverinfo: "skip" },
      { type: "scatter", mode: "lines", name: `${metricLabel[k]} breach`, x, y: x.map(() => last.breach_limit), line: { color, dash: "dash", width: 1 }, hoverinfo: "skip" },
    ];
  };
  const palette = [COLORS.accent, COLORS.teal, "#7C3AED", COLORS.orange];
  const perf = [...perfKeys.map((k, i) => ({ type: "scatter", mode: "lines+markers", name: metricLabel[k], x, y: s[k].map((p: any) => p.value), line: { color: palette[i], width: 2 },
    marker: { size: 6, color: s[k].map((p: any) => (p.status === "Breach" ? COLORS.red : p.status === "Warning" ? "#F59E0B" : palette[i])) } })), ...limitLines("recall", COLORS.red)];
  const psi = ["psi", "max_feature_psi", "dq_exception_rate"].filter((k) => s[k]).map((k, i) => ({ type: "scatter", mode: "lines+markers", name: metricLabel[k], x,
    y: s[k].map((p: any) => p.value), line: { color: [COLORS.accent, COLORS.orange, "#7C3AED"][i], width: 2 }, yaxis: k === "dq_exception_rate" ? "y2" : "y" }));
  const shapes = [...shading(x, ref),
    { type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.1, y1: 0.1, line: { color: "#F59E0B", dash: "dot", width: 1 } },
    { type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.25, y1: 0.25, line: { color: COLORS.red, dash: "dash", width: 1 } }];
  return (
    <div className="grid gap-4 2xl:grid-cols-2">
      <Panel title="Performance over time" actions={<span className="text-[11.5px] text-muted">Grey band: reference window. Markers turn amber or red on warnings and breaches.</span>}>
        {perfKeys.length ? <Plot ariaLabel="Line chart of precision and recall by period" data={perf} height={300}
          layout={{ shapes: shading(x, ref), xaxis: periodAxis, yaxis: { range: [0, 1.02], tickformat: ".0%", gridcolor: "#EEF2F7" } }} /> : <Empty>No classification metrics.</Empty>}
      </Panel>
      <Panel title="Stability and data quality" actions={<span className="text-[11.5px] text-muted">PSI bands at 0.10 and 0.25</span>}>
        <Plot ariaLabel="Line chart of score PSI, maximum feature PSI and data quality exception rate" data={psi} height={300}
          layout={{ shapes, xaxis: periodAxis, yaxis: { title: { text: "PSI" }, rangemode: "tozero", gridcolor: "#EEF2F7" },
            yaxis2: { title: { text: "DQ exceptions" }, overlaying: "y", side: "right", tickformat: ".1%", rangemode: "tozero", showgrid: false } }} />
      </Panel>
    </div>
  );
}

function DriftView({ run }: { run: any }) {
  const psiM = run.metrics.find((m: any) => m.metric === "psi");
  const bins = psiM?.details?.bins ?? [];
  const dq = run.metrics.find((m: any) => m.metric === "dq_exception_rate")?.details?.by_rule ?? {};
  const [feat, setFeat] = useState<string | null>(null);
  const fsel = run.drift.find((d: any) => d.feature === feat) ?? run.drift[0];
  const label = (b: any) => (b.lower === undefined ? String(b.bin) : `${b.lower === null ? "−∞" : dec(b.lower, 3)} to ${b.upper === null ? "∞" : dec(b.upper, 3)}`);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 2xl:grid-cols-2">
        <Panel title={`Score distribution, reference vs ${run.period}`} actions={<span className="text-[12px]">PSI <b>{dec(psiM?.value)}</b> · {psiM?.details?.band}</span>}>
          <Plot ariaLabel="Bar chart comparing reference and current score shares by decile bin" height={280} data={[
            { type: "bar", name: "Reference", x: bins.map((b: any) => b.bin), y: bins.map((b: any) => b.expected_share), marker: { color: "#CBD5E1" },
              hovertext: bins.map(label), hoverinfo: "text+y" },
            { type: "bar", name: run.period, x: bins.map((b: any) => b.bin), y: bins.map((b: any) => b.actual_share), marker: { color: COLORS.accent },
              hovertext: bins.map(label), hoverinfo: "text+y" }]}
            layout={{ barmode: "group", xaxis: { title: { text: "Reference decile bin" }, dtick: 1 }, yaxis: { tickformat: ".0%", gridcolor: "#EEF2F7" } }} />
        </Panel>
        {fsel && (
          <Panel title={`Input feature: ${fsel.feature}`} actions={<span className="text-[12px]">{fsel.test} · PSI <b>{dec(fsel.psi)}</b> · <StatusBadge s={fsel.level === "Stable" ? "Within limits" : fsel.level === "Moderate" ? "Warning" : "Breach"} /></span>}>
            <Plot ariaLabel={`Bar chart comparing reference and current distribution of ${fsel.feature}`} height={280} data={[
              { type: "bar", name: "Reference", x: fsel.bins.map((b: any) => (fsel.feature_type === "numeric" ? `Bin ${b.bin}` : b.bin)), y: fsel.bins.map((b: any) => b.expected_share), marker: { color: "#CBD5E1" } },
              { type: "bar", name: run.period, x: fsel.bins.map((b: any) => (fsel.feature_type === "numeric" ? `Bin ${b.bin}` : b.bin)), y: fsel.bins.map((b: any) => b.actual_share), marker: { color: COLORS.orange } }]}
              layout={{ barmode: "group", yaxis: { tickformat: ".0%", gridcolor: "#EEF2F7" } }} />
          </Panel>)}
      </div>
      <Panel title="Input drift tests" bodyClass="" actions={<span className="text-[11.5px] text-muted">Flag needs p &lt; 0.01 and a material effect, or PSI ≥ 0.10</span>}>
        <DataTable rowKey={(d: any) => d.feature} rows={run.drift} onRowClick={(d: any) => setFeat(d.feature)} empty="No input features monitored for this model."
          columns={[{ key: "f", header: "Feature", render: (d: any) => <span className="font-medium">{d.feature}</span> },
            { key: "t", header: "Type", render: (d: any) => d.feature_type }, { key: "test", header: "Test", render: (d: any) => d.test },
            { key: "s", header: "Statistic", align: "right", render: (d: any) => dec(d.statistic, 4) },
            { key: "p", header: "p-value", align: "right", render: (d: any) => (d.p_value < 0.0001 ? "<0.0001" : dec(d.p_value, 4)) },
            { key: "e", header: "Effect size", align: "right", render: (d: any) => dec(d.effect_size, 3) },
            { key: "psi", header: "PSI", align: "right", sort: (d: any) => d.psi, render: (d: any) => dec(d.psi) },
            { key: "l", header: "Level", render: (d: any) => <Badge tone={d.level === "Stable" ? "green" : d.level === "Moderate" ? "amber" : "red"}>{d.level}</Badge> }]} />
      </Panel>
      <Panel title={`Data quality exceptions in ${run.period}`}>
        {Object.keys(dq).length ? (
          <ul className="grid gap-1 sm:grid-cols-2">{Object.entries(dq).map(([k, n]) => <li key={k} className="flex justify-between border-b border-line py-1"><span>{k.replace(/_/g, " ")}</span><b>{String(n)}</b></li>)}</ul>
        ) : <Empty>No records failed a data quality rule.</Empty>}
      </Panel>
    </div>
  );
}

function BreachTable({ data, modelId }: { data: any[]; modelId: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [showAll, setShowAll] = useState(false);
  const rows = showAll ? data : data.filter((b) => b.status !== "Resolved");
  const act = (b: any, path: string) => (c: string) => api(`/monitoring/breaches/${b.breach_id}/${path}`, { body: { notes: c } })
    .then(() => qc.invalidateQueries({ queryKey: ["breaches", modelId] }));
  return (
    <Panel bodyClass="" title="Threshold breaches and warnings" actions={<label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />Include resolved</label>}>
      <DataTable rowKey={(b: any) => b.breach_id} rows={rows} empty="No open breaches."
        columns={[{ key: "p", header: "Period", className: "whitespace-nowrap", render: (b: any) => b.period },
          { key: "m", header: "Metric", render: (b: any) => <span className="font-medium">{metricLabel[b.metric] ?? b.metric}</span> },
          { key: "v", header: "Value", align: "right", render: (b: any) => fmtMetric(b.metric, b.value) },
          { key: "lim", header: "Limits (warn / breach)", render: (b: any) => `${fmtMetric(b.metric, b.warning_limit)} / ${fmtMetric(b.metric, b.breach_limit)}` },
          { key: "lvl", header: "Level", render: (b: any) => <StatusBadge s={b.level} /> },
          { key: "sev", header: "Severity", render: (b: any) => <span title={b.severity_rationale}><SeverityBadge s={b.severity} /></span> },
          { key: "c", header: "Periods", align: "right", render: (b: any) => b.consecutive_periods },
          { key: "s", header: "Status", render: (b: any) => <div><StatusBadge s={b.status} />{b.notes && <div className="max-w-[220px] text-[11.5px] text-muted">{b.notes}</div>}</div> },
          { key: "a", header: "", render: (b: any) => b.status === "Resolved" || !can("breach:acknowledge") ? null : (
            <div className="flex gap-1">
              {b.status === "Open" && <ActionButton label="Acknowledge" title={`Acknowledge ${b.breach_id}`} commentLabel="Notes" minComment={5} onRun={act(b, "acknowledge")} />}
              <ActionButton label="Resolve" title={`Resolve ${b.breach_id}`} commentLabel="Resolution notes" minComment={5} onRun={act(b, "resolve")} />
            </div>) }]} />
    </Panel>
  );
}

function ThresholdEditor({ modelId }: { modelId: string }) {
  const qc = useQueryClient();
  const { user, can } = useAuth();
  const t = useQuery({ queryKey: ["thresholds", modelId], queryFn: () => api(`/monitoring/models/${modelId}/thresholds`) });
  const model = useQuery({ queryKey: ["model", modelId], queryFn: () => api(`/models/${modelId}`) });
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { if (t.data) setRows(t.data.map((x: any) => ({ ...x }))); }, [t.data]);
  const save = useMutation({ mutationFn: () => api(`/monitoring/models/${modelId}/thresholds`, { method: "PUT",
    body: { items: rows.map((r) => ({ metric: r.metric, warning_limit: Number(r.warning_limit), breach_limit: Number(r.breach_limit), rationale: r.rationale, is_active: r.is_active })) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thresholds", modelId] }) });
  const editable = can("monitoring:configure") && (user?.role === "admin" || model.data?.can_edit);
  const changed = useMemo(() => JSON.stringify(rows) !== JSON.stringify(t.data ?? []), [rows, t.data]);
  if (t.isLoading) return <Spinner />;
  const set = (i: number, k: string, v: unknown) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <Panel title="KPI and KRI thresholds" actions={editable ? <button className="btn-primary" disabled={!changed || save.isPending} onClick={() => save.mutate()}>Save changes</button> : <span className="text-[12px] text-muted">Read only for your role</span>}>
      {!editable && <div className="mb-3"><Notice>Model owners of this model and administrators can change thresholds. Changes are audited and apply from the next monitoring run.</Notice></div>}
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0">
          <thead><tr>{["Metric", "Type", "Adverse when", "Warning", "Breach", "Active", "Rationale"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={r.metric}>
              <td className="td font-medium">{metricLabel[r.metric] ?? r.metric}</td>
              <td className="td"><Badge tone={r.kind === "KPI" ? "blue" : "slate"}>{r.kind}</Badge></td>
              <td className="td text-muted">{r.direction === "min" ? "below" : "above"}</td>
              <td className="td"><input className="input w-24" type="number" step="0.01" disabled={!editable} value={r.warning_limit} onChange={(e) => set(i, "warning_limit", e.target.value)} aria-label={`${r.metric} warning limit`} /></td>
              <td className="td"><input className="input w-24" type="number" step="0.01" disabled={!editable} value={r.breach_limit} onChange={(e) => set(i, "breach_limit", e.target.value)} aria-label={`${r.metric} breach limit`} /></td>
              <td className="td"><input type="checkbox" disabled={!editable} checked={r.is_active} onChange={(e) => set(i, "is_active", e.target.checked)} aria-label={`${r.metric} active`} /></td>
              <td className="td"><textarea className="textarea min-w-[280px]" rows={2} disabled={!editable} value={r.rationale} onChange={(e) => set(i, "rationale", e.target.value)} /></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="mt-3"><ErrorBox error={save.error} /></div>
    </Panel>
  );
}

function MethodologyDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const q = useQuery({ queryKey: ["methodology"], queryFn: () => api("/monitoring/methodology"), enabled: open });
  return (
    <Drawer open={open} onClose={onClose} title={<span className="text-[15px] font-semibold">Monitoring methodology</span>}>
      {!q.data ? <Spinner /> : (
        <div className="space-y-5 p-5 text-[13px] leading-5">
          <div>
            <h3 className="mb-2 font-semibold">Metric definitions</h3>
            <DataTable rowKey={(m: any) => m.metric} rows={q.data.metrics} columns={[
              { key: "n", header: "Metric", render: (m: any) => <span className="font-medium">{m.name}</span> },
              { key: "f", header: "Formula", render: (m: any) => <code className="text-[12px]">{m.formula}</code> },
              { key: "m", header: "Meaning", render: (m: any) => <span className="text-[12.5px]">{m.meaning}</span> }]} />
          </div>
          {[["Population Stability Index", q.data.psi], ["Drift tests", q.data.drift], ["Breach severity", q.data.severity]].map(([t, body]) => (
            <div key={t}><h3 className="mb-1 font-semibold">{t}</h3><pre className="whitespace-pre-wrap rounded-md bg-sunken p-3 font-sans text-[12.5px]">{body}</pre></div>))}
          <div>
            <h3 className="mb-1 font-semibold">Data quality rules</h3>
            {Object.entries(q.data.data_quality_rules).map(([feed, rules]: any) => (
              <div key={feed} className="mb-2"><div className="kv-k">{feed}</div>
                <ul className="list-disc pl-5">{rules.map((r: any) => <li key={r.code}><code>{r.code}</code>: {r.description}</li>)}</ul></div>))}
          </div>
          <div>
            <h3 className="mb-1 font-semibold">Model operating parameters</h3>
            <pre className="max-h-80 overflow-auto rounded-md bg-sunken p-3 text-[11.5px]">{JSON.stringify(q.data.model_parameters, null, 2)}</pre>
          </div>
          <Notice>Recall uses synthetic ground truth for every record. Production banks cannot observe missed cases directly; they estimate recall with below-the-line testing, look-backs and SAR back-testing.</Notice>
        </div>)}
    </Drawer>
  );
}

