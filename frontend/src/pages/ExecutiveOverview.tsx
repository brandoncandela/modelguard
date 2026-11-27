import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { DataTable } from "../components/ui/DataTable";
import { ErrorBox, Kpi, Panel, RiskBadge, SeverityBadge, Spinner, StatusBadge } from "../components/ui";
import { COLORS, Plot, periodAxis, refBand } from "../components/charts/Plot";
import { date, fmtMetric, metricLabel } from "../lib/format";

export default function ExecutiveOverview() {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api("/dashboard/executive") });
  const charts = useMemo(() => {
    if (!q.data) return null;
    const ps = q.data.trends.periods as any[];
    const x = ps.map((p) => p.period);
    const ref = ps.filter((p) => p.is_reference).map((p) => p.period);
    const shade = refBand(ref.length);
    const annot = ref.length ? [{ x: -0.4, y: 0.98, xref: "x", yref: "paper", text: "Reference window", showarrow: false,
      xanchor: "left", yanchor: "top", font: { size: 10, color: "#64748B" } }] : [];
    const sev = (s: string) => ps.map((p) => p.breaches_by_severity?.[s] ?? 0);
    const q4 = q.data.trends.validation_outcomes_by_quarter as Record<string, Record<string, number>>;
    const quarters = Object.keys(q4);
    return {
      breaches: [
        { type: "bar", name: "Critical", x, y: sev("Critical"), marker: { color: COLORS.red } },
        { type: "bar", name: "High", x, y: sev("High"), marker: { color: COLORS.orange } },
        { type: "bar", name: "Medium", x, y: sev("Medium"), marker: { color: "#F59E0B" } },
      ],
      findings: [
        { type: "scatter", mode: "lines+markers", name: "Open", x, y: ps.map((p) => p.open_findings), line: { color: COLORS.accent } },
        { type: "scatter", mode: "lines+markers", name: "Past target", x, y: ps.map((p) => p.open_findings_overdue), line: { color: COLORS.red } },
      ],
      alerts: [
        { type: "bar", name: "Alerts", x, y: ps.map((p) => p.alerts), marker: { color: COLORS.light } },
        { type: "bar", name: "Escalated to case", x, y: ps.map((p) => p.alerts_escalated), marker: { color: COLORS.accent } },
      ],
      validations: ["Approved", "Conditionally Approved", "Rejected"].map((s, i) => ({
        type: "bar", name: s, x: quarters, y: quarters.map((qq) => q4[qq][s] ?? 0),
        marker: { color: [COLORS.teal, "#F59E0B", COLORS.red][i] },
      })),
      shapes: shade, annotations: annot,
    };
  }, [q.data]);

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  const k = d.kpis;
  const sev = k.open_breaches_by_severity ?? {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Kpi label="Total models" value={k.total_models} note={`${k.approval_status_counts?.Approved ?? 0} approved · ${k.approval_status_counts?.["Conditionally Approved"] ?? 0} conditional`} onClick={() => nav("/inventory")} />
        <Kpi label="High-risk models" value={k.high_risk_models} note={`${Math.round((100 * k.high_risk_models) / k.total_models)}% of inventory`} onClick={() => nav("/inventory?risk=High")} />
        <Kpi label="Awaiting validation" value={k.models_awaiting_validation} note="validation under way" onClick={() => nav("/validations")} />
        <Kpi label="Overdue validations" value={k.overdue_validations} tone={k.overdue_validations ? "bad" : "ok"} note={`${k.validations_due_90_days} more due in 90 days`} onClick={() => nav("/inventory?due=overdue")} />
        <Kpi label="Breaching thresholds" value={k.models_breaching_thresholds} tone={k.models_breaching_thresholds ? "bad" : "ok"} note={`${sev.Critical ?? 0} Critical · ${sev.High ?? 0} High open`} onClick={() => nav("/monitoring")} />
        <Kpi label="Open critical findings" value={k.open_critical_findings} tone={k.open_critical_findings ? "bad" : "ok"} note={`${k.open_high_findings} High`} onClick={() => nav("/findings?severity=Critical")} />
        <Kpi label="Outstanding remediation" value={k.outstanding_remediation_actions} note={`${k.overdue_remediation_actions} past target`} tone={k.overdue_remediation_actions ? "warn" : undefined} onClick={() => nav("/findings")} />
        <Kpi label="AI awaiting approval" value={k.ai_systems_awaiting_approval} note={`of ${k.ai_systems_total} AI systems`} onClick={() => nav("/ai")} />
        <Kpi label="Documentation complete" value={`${k.documentation_completeness_pct}%`} note={`${k.documentation_complete_models} of ${k.total_models} entries fully complete`} onClick={() => nav("/inventory")} />
        <Kpi label="Control tests passing" value={`${d.controls.tests_passing}/${d.controls.tests_total}`} tone={d.controls.tests_passing < d.controls.tests_total ? "warn" : "ok"} note={`${d.controls.requirements_with_gaps} requirements partly covered`} onClick={() => nav("/regulatory")} />
      </div>

      {charts && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel title="Threshold breaches by period" actions={<span className="text-[11.5px] text-muted">Breach level only, latest run per model</span>}>
            <Plot ariaLabel="Stacked bar chart of threshold breaches by period and severity" data={charts.breaches}
              layout={{ barmode: "stack", shapes: charts.shapes, annotations: charts.annotations, xaxis: periodAxis, yaxis: { title: { text: "Breaches" }, gridcolor: "#EEF2F7", rangemode: "tozero" } }} />
          </Panel>
          <Panel title="Open findings at each month end" actions={<span className="text-[11.5px] text-muted">Reconstructed from dated workflow events</span>}>
            <Plot ariaLabel="Line chart of open and overdue findings by month" data={charts.findings} layout={{ xaxis: periodAxis, yaxis: { rangemode: "tozero", gridcolor: "#EEF2F7" } }} />
          </Panel>
          <Panel title="Alert volume and escalations">
            <Plot ariaLabel="Bar chart of alerts and escalations by period" data={charts.alerts} layout={{ barmode: "overlay", shapes: charts.shapes, xaxis: periodAxis }} />
          </Panel>
          <Panel title="Validation outcomes by quarter">
            <Plot ariaLabel="Stacked bar chart of validation decisions by quarter" data={charts.validations} layout={{ barmode: "stack", yaxis: { dtick: 1, gridcolor: "#EEF2F7" } }} />
          </Panel>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Models breaching thresholds" bodyClass="">
          <DataTable rowKey={(r: any) => r.model_id} rows={d.models_in_breach} onRowClick={(r: any) => nav(`/monitoring/${r.model_id}`)}
            empty="No model is in breach."
            columns={[
              { key: "model_id", header: "Model", render: (r: any) => <><div className="font-medium whitespace-nowrap">{r.model_id}</div><div className="text-[11.5px] text-muted">{r.name}</div></> },
              { key: "period", header: "Source", render: (r: any) => <span className="whitespace-nowrap text-muted">{r.source === "monitoring" ? r.period : r.source}</span> },
              { key: "metrics", header: "Breached metrics", render: (r: any) => (
                <div className="flex flex-wrap gap-1">{r.metrics.map((m: any) => (
                  <span key={m.metric} className="inline-flex items-center gap-1 text-[12px]">{metricLabel[m.metric] ?? m.metric} {fmtMetric(m.metric, m.value)}
                    {m.severity !== "Breach" && <SeverityBadge s={m.severity} />}</span>))}</div>) },
              { key: "worst", header: "Worst", render: (r: any) => <SeverityBadge s={r.worst_severity} />, sort: (r: any) => r.worst_severity },
            ]} />
        </Panel>
        <Panel title="Critical and High findings" bodyClass="">
          <DataTable rowKey={(r: any) => r.finding_id} rows={d.critical_and_high_findings} onRowClick={(r: any) => nav(`/findings/${r.finding_id}`)} maxHeight="320px" dense
            columns={[
              { key: "finding_id", header: "Finding", render: (r: any) => <span className="font-medium whitespace-nowrap">{r.finding_id}</span> },
              { key: "model_id", header: "Model", className: "whitespace-nowrap" },
              { key: "severity", header: "Severity", render: (r: any) => <SeverityBadge s={r.severity} /> },
              { key: "status", header: "Status", render: (r: any) => <StatusBadge s={r.status} /> },
              { key: "target", header: "Target", render: (r: any) => <span className={r.overdue_days ? "font-medium text-bad" : ""}>{date(r.target_date)}{r.overdue_days ? ` (+${r.overdue_days}d)` : ""}</span>, sort: (r: any) => r.target_date },
            ]} />
        </Panel>
        <Panel title="Validations due within 90 days or overdue" bodyClass="">
          <DataTable rowKey={(r: any) => r.model_id} rows={d.upcoming_validations} onRowClick={(r: any) => nav(`/inventory/${r.model_id}`)} dense
            columns={[
              { key: "model_id", header: "Model", render: (r: any) => <><span className="font-medium whitespace-nowrap">{r.model_id}</span> <span className="text-muted">{r.name}</span></> },
              { key: "risk", header: "Risk", render: (r: any) => <RiskBadge r={r.risk_rating} /> },
              { key: "due", header: "Next validation", render: (r: any) => date(r.next_validation_date) },
              { key: "days", header: "Days", align: "right", render: (r: any) => <span className={r.days < 0 ? "font-medium text-bad" : ""}>{r.days}</span> },
            ]} />
        </Panel>
        <Panel title="AI systems awaiting approval" bodyClass="">
          <DataTable rowKey={(r: any) => r.system_id} rows={d.ai_awaiting_approval} onRowClick={(r: any) => nav(`/ai/${r.system_id}`)} dense
            columns={[
              { key: "system_id", header: "System", render: (r: any) => <><span className="font-medium whitespace-nowrap">{r.system_id}</span> <span className="text-muted">{r.name}</span></> },
              { key: "approval_status", header: "Status", render: (r: any) => <StatusBadge s={r.approval_status} /> },
              { key: "classification", header: "EU AI Act (readiness view)", render: (r: any) => <span className="text-[12px]">{r.classification}</span> },
            ]} />
        </Panel>
      </div>
    </div>
  );
}
