"""PDF rendering for management and validation reports (ReportLab, no external services)."""
from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
ACCENT = colors.HexColor("#1D4ED8")
TEAL = colors.HexColor("#0F766E")
LINE = colors.HexColor("#E5E7EB")
ZEBRA = colors.HexColor("#F8FAFC")
RED = colors.HexColor("#B91C1C")
AMBER = colors.HexColor("#B45309")
ORANGE = colors.HexColor("#EA580C")
YELLOW = colors.HexColor("#F59E0B")
SEV = {"Critical": RED, "High": ORANGE, "Medium": AMBER, "Low": MUTED, "Breach": RED,
       "Warning": AMBER, "Within limits": TEAL, "Pass": TEAL, "Fail": RED}

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK,
                    spaceAfter=2)
H2 = ParagraphStyle("H2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                    textColor=ACCENT, spaceBefore=12, spaceAfter=5)
BODY = ParagraphStyle("Body", parent=_ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK,
                      alignment=TA_LEFT)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=7.6, leading=9.8)
MUTE = ParagraphStyle("Mute", parent=BODY, fontSize=8, leading=11, textColor=MUTED)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=7.6, leading=9.6)
CELLB = ParagraphStyle("CellB", parent=CELL, fontName="Helvetica-Bold")


def esc(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, (date, datetime)):
        return v.strftime("%d %b %Y")
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(v: Optional[float], digits: int = 1) -> str:
    return "-" if v is None else f"{v * 100:.{digits}f}%"


class NumberedCanvas(pdfcanvas.Canvas):
    footer_text = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(MUTED)
            self.drawString(0.7 * inch, 0.45 * inch, self.footer_text)
            self.drawRightString(letter[0] - 0.7 * inch, 0.45 * inch, f"Page {self._pageNumber} of {n}")
            self.setStrokeColor(LINE)
            self.line(0.7 * inch, 0.6 * inch, letter[0] - 0.7 * inch, 0.6 * inch)
            super().showPage()
        super().save()


def table(rows: List[List[Any]], widths: List[float], header: bool = True, status_col: Optional[int] = None) -> Table:
    data = []
    for i, r in enumerate(rows):
        style = CELLB if (header and i == 0) else CELL
        data.append([c if isinstance(c, (Paragraph, Drawing)) else Paragraph(esc(c), style) for c in r])
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1 if header else 0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT)]
    for i in range(1 if header else 0, len(rows)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
        if status_col is not None:
            col = SEV.get(str(rows[i][status_col]))
            if col is not None:
                cmds.append(("TEXTCOLOR", (status_col, i), (status_col, i), col))
    t.setStyle(TableStyle(cmds))
    return t


def kpi_grid(items: List[tuple]) -> Table:
    cells = []
    row = []
    for label, value, note in items:
        block = [Paragraph(f'<font size="7.5" color="#6B7280">{esc(label).upper()}</font>', CELL),
                 Paragraph(f'<font size="15"><b>{esc(value)}</b></font>', CELL),
                 Paragraph(f'<font size="7" color="#6B7280">{esc(note)}</font>', CELL)]
        row.append(block)
        if len(row) == 4:
            cells.append(row)
            row = []
    if row:
        cells.append(row + [""] * (4 - len(row)))
    t = Table(cells, colWidths=[1.77 * inch] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def bar_chart(labels: List[str], series: List[List[float]], names: List[str], title: str,
              palette: Iterable = (ACCENT, TEAL, AMBER, RED), stacked: bool = False) -> Drawing:
    d = Drawing(7.1 * inch, 1.9 * inch)
    d.add(String(0, 1.78 * inch, title, fontName="Helvetica-Bold", fontSize=8, fillColor=INK))
    c = VerticalBarChart()
    c.x, c.y, c.width, c.height = 28, 22, 7.1 * inch - 40, 1.9 * inch - 50
    c.data = series
    c.categoryAxis.categoryNames = labels
    c.categoryAxis.labels.fontSize = 6.5
    c.categoryAxis.labels.fontName = "Helvetica"
    c.categoryAxis.labels.angle = 0
    c.valueAxis.labels.fontSize = 6.5
    c.valueAxis.labels.fontName = "Helvetica"
    c.valueAxis.valueMin = 0
    c.valueAxis.gridStrokeColor = LINE
    c.valueAxis.visibleGrid = True
    c.categoryAxis.style = "stacked" if stacked else "parallel"
    for i, col in enumerate(list(palette)[: len(series)]):
        c.bars[i].fillColor = col
        c.bars[i].strokeColor = None
    c.barSpacing = 1
    d.add(c)
    x = 7.1 * inch - 10
    for name, col in reversed(list(zip(names, palette))):
        w = 6 + len(name) * 3.6
        x -= w + 10
        d.add(String(x + 9, 1.78 * inch, name, fontName="Helvetica", fontSize=6.8, fillColor=MUTED))
        from reportlab.graphics.shapes import Rect

        d.add(Rect(x, 1.78 * inch - 1, 6, 6, fillColor=col, strokeColor=None))
    return d


def line_chart(labels: List[str], series: Dict[str, List[Optional[float]]], title: str,
               limit: Optional[float] = None) -> Drawing:
    d = Drawing(7.1 * inch, 1.9 * inch)
    d.add(String(0, 1.78 * inch, title, fontName="Helvetica-Bold", fontSize=8, fillColor=INK))
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 30, 22, 7.1 * inch - 44, 1.9 * inch - 50
    data, cols = [], [ACCENT, TEAL, AMBER, RED]
    for vals in series.values():
        data.append([(i, v) for i, v in enumerate(vals) if v is not None])
    if limit is not None:
        data.append([(0, limit), (len(labels) - 1, limit)])
    lp.data = data
    for i in range(len(series)):
        lp.lines[i].strokeColor = cols[i % 4]
        lp.lines[i].strokeWidth = 1.4
    if limit is not None:
        lp.lines[len(series)].strokeColor = RED
        lp.lines[len(series)].strokeDashArray = [3, 2]
        lp.lines[len(series)].strokeWidth = 0.8
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, max(len(labels) - 1, 1)
    lp.xValueAxis.valueSteps = list(range(len(labels)))
    lp.xValueAxis.labelTextFormat = lambda v: labels[int(v)][2:] if 0 <= int(v) < len(labels) else ""
    lp.xValueAxis.labels.fontSize = 6.5
    lp.xValueAxis.labels.fontName = "Helvetica"
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = 1
    lp.yValueAxis.labels.fontSize = 6.5
    lp.yValueAxis.labels.fontName = "Helvetica"
    lp.yValueAxis.visibleGrid = True
    lp.yValueAxis.gridStrokeColor = LINE
    d.add(lp)
    x = 7.1 * inch - 10
    for i, name in reversed(list(enumerate(series))):
        w = 6 + len(name) * 3.6
        x -= w + 10
        d.add(String(x + 9, 1.78 * inch, name, fontName="Helvetica", fontSize=6.8, fillColor=MUTED))
        from reportlab.graphics.shapes import Rect

        d.add(Rect(x, 1.78 * inch - 1, 6, 6, fillColor=cols[i % 4], strokeColor=None))
    return d


def header(story: List, institution: str, title: str, subtitle: str, report_id: str, as_of: str, by: str) -> None:
    story.append(Paragraph(f'<font color="#1D4ED8"><b>MODELGUARD</b></font>  <font color="#6B7280">{esc(institution)}</font>',
                           MUTE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(esc(title), H1))
    story.append(Paragraph(esc(subtitle), MUTE))
    story.append(Spacer(1, 4))
    meta = table([["Report", "As of", "Prepared by", "Generated"],
                  [report_id, as_of, by, datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")]],
                 [1.6, 1.6, 2.2, 1.7])
    story.append(meta)


def build(doc_title: str, footer: str, story: List) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.8 * inch, title=doc_title, author="ModelGuard",
                            subject="Synthetic data; not a certification of regulatory compliance")

    class _C(NumberedCanvas):
        footer_text = footer

    doc.build(story, canvasmaker=_C)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------
# Section builders
# ------------------------------------------------------------------------------------------------


def sec_summary(story, pack):
    story.append(Paragraph("Executive summary", H2))
    story.append(Paragraph(esc(pack["summary"]), BODY))


def sec_kris(story, k):
    story.append(Paragraph("Key risk indicators", H2))
    sev = k["open_breaches_by_severity"]
    story.append(kpi_grid([
        ("Models in inventory", k["total_models"], f"{k['high_risk_models']} rated High risk"),
        ("Awaiting validation", k["models_awaiting_validation"], "validation under way"),
        ("Overdue validations", k["overdue_validations"], f"{k['validations_due_90_days']} more due in 90 days"),
        ("Breaching thresholds", k["models_breaching_thresholds"],
         f"{sev.get('Critical', 0)} Critical, {sev.get('High', 0)} High open breaches"),
        ("Open Critical findings", k["open_critical_findings"], f"{k['open_high_findings']} High"),
        ("Remediation actions", k["outstanding_remediation_actions"], f"{k['overdue_remediation_actions']} past target"),
        ("AI awaiting approval", k["ai_systems_awaiting_approval"], f"of {k['ai_systems_total']} AI systems"),
        ("Documentation", f"{k['documentation_completeness_pct']}%",
         f"{k['documentation_complete_models']} entries fully complete"),
    ]))


def sec_trend_charts(story, trends):
    ps = trends["periods"]
    labels = [p["period"][2:] for p in ps]
    sev = ["Critical", "High", "Medium"]
    series = [[p["breaches_by_severity"].get(s, 0) for p in ps] for s in sev]
    story.append(Spacer(1, 6))
    story.append(bar_chart(labels, series, sev, "Threshold breaches by period and severity",
                           palette=(RED, ORANGE, YELLOW), stacked=True))
    story.append(bar_chart(labels, [[p["open_findings"] for p in ps], [p["open_findings_overdue"] for p in ps]],
                           ["Open", "Past target"], "Open findings at each month end"))


def sec_inventory_changes(story, changes):
    story.append(Paragraph("Model inventory changes (last 90 days)", H2))
    if not changes:
        story.append(Paragraph("No user changes to inventory records in the period. Seeded records were loaded by the "
                               "system and are excluded.", MUTE))
        return
    rows = [["Date", "By", "Change", "Entry", "Summary"]] + [
        [c["occurred_at"], c["actor"], c["action"].replace("_", " ").title(), c["entity"], c["summary"]]
        for c in changes[:25]]
    story.append(table(rows, [0.9, 0.8, 1.3, 1.0, 3.1]))


def sec_validation_outcomes(story, outcomes, pipeline):
    story.append(Paragraph("Validation outcomes (last 12 months)", H2))
    rows = [["Validation", "Model", "Type", "Decision", "Rating", "Decided", "Conditions or reason"]] + [
        [v["validation_id"], v["model_id"], v["type"], v["status"], v["rating"], v["decided_on"],
         v["conditions"] or v.get("reason") or "-"] for v in outcomes]
    story.append(table(rows, [0.95, 0.9, 0.7, 0.95, 1.0, 0.75, 1.85]))
    if pipeline:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Validation pipeline", BODY))
        rows = [["Validation", "Model", "Status", "Lead validator", "Scheduled end"]] + [
            [v["validation_id"], v["model_id"], v["status"], v["lead"] or "Not assigned", v["scheduled_end"]]
            for v in pipeline]
        story.append(table(rows, [1.2, 1.1, 1.3, 2.0, 1.5]))


def sec_findings(story, f):
    story.append(Paragraph("Critical and High findings", H2))
    rows = [["Finding", "Model", "Severity", "Status", "Owner", "Target", "Past target"]] + [
        [x["finding_id"], x["model_id"], x["severity"], x["status"], x["owner"], x["target_date"],
         f"{x['overdue_days']} days" if x["overdue_days"] else "-"] for x in f["critical_and_high_open"]]
    story.append(table(rows, [0.95, 0.9, 0.7, 1.1, 1.2, 0.85, 0.75], status_col=2))
    sc = f["status_counts"]
    order = ["Open", "Response Submitted", "In Remediation", "Pending Validation", "Closed", "Risk Accepted"]
    story.append(KeepTogether([Paragraph("Remediation progress", H2), bar_chart([o.replace("Response Submitted", "Response").replace("Pending Validation", "Pending val.")
                            for o in order], [[sc.get(o, 0) for o in order]], ["Findings"],
                           "Findings by status")]))
    story.append(Paragraph(
        f"{f['open']} of {f['total']} findings are open; {len(f['overdue'])} are past target; "
        f"{f['closed_last_180_days']} were closed in the last 180 days after independent verification.", BODY))


def sec_ai(story, pack_ai):
    story.append(Paragraph("AI governance status", H2))
    rows = [["System", "Name", "EU AI Act class (readiness view)", "Approval", "Deployment", "Bias test"]] + [
        [s["system_id"], s["name"], s["classification"], s["approval"], s["deployment"], s["bias"]]
        for s in pack_ai["systems"]]
    story.append(table(rows, [0.6, 2.0, 1.75, 1.05, 0.8, 0.9]))
    if pack_ai["evaluations"]:
        story.append(Spacer(1, 6))
        rows = [["Run", "System", "Version", "Factual acc.", "Hallucination", "Policy", "Result"]] + [
            [e["run_id"], e["system_id"], e["version"], pct(e["metrics"].get("factual_accuracy")),
             pct(e["metrics"].get("hallucination_rate")), pct(e["metrics"].get("policy_compliance")),
             "Pass" if e["passed"] else "Fail"] for e in pack_ai["evaluations"]]
        story.append(table(rows, [0.9, 0.7, 1.0, 1.0, 1.0, 0.9, 0.8], status_col=6))


def sec_monitoring(story, rows):
    story.append(Paragraph("Model performance (latest period)", H2))
    head = ["Model", "Status", "Records", "Alerts", "Precision", "Recall", "PSI", "DQ exc.", "Drifting inputs"]
    body = []
    for r in rows:
        m = r["metrics"]
        body.append([r["model_id"], r["status"], f"{r['records']:,}",
                     f"{r['alerts']:,}" if r.get("alerting", True) else "n/a",
                     pct(m.get("precision", {}).get("value")), pct(m.get("recall", {}).get("value")),
                     esc(m.get("psi", {}).get("value")), pct(m.get("dq_exception_rate", {}).get("value"), 2),
                     ", ".join(d["feature"] for d in r["drifting_features"]) or "-"])
    story.append(table([head] + body, [0.95, 0.75, 0.6, 0.5, 0.65, 0.6, 0.5, 0.6, 1.95], status_col=1))


def sec_controls(story, controls, title):
    story.append(Paragraph(title, H2))
    rows = [["Control", "Name", "Status", "Latest test", "Gaps"]] + [
        [c["control_id"], c["name"], c["status"], c["latest_test"], c["gaps"] or "-"] for c in controls]
    story.append(table(rows, [0.6, 1.8, 1.1, 0.75, 2.85], status_col=3))


def sec_recommendations(story, recs):
    story.append(Paragraph("Management recommendations", H2))
    for i, r in enumerate(recs, 1):
        story.append(Paragraph(f"{i}. {esc(r)}", BODY))
        story.append(Spacer(1, 2))


def sec_disclaimer(story, text):
    story.append(Spacer(1, 10))
    story.append(Paragraph(esc(text), MUTE))


def render_management(report_type: str, report_id: str, packs: Dict[str, Dict], trends: Dict, institution: str,
                      prepared_by: str) -> bytes:
    story: List = []
    titles = {"executive": "Executive Model Risk and AI Governance Report", "mrmc": "Model Risk Management Committee Pack",
              "fcmoc": "Financial Crime Model Oversight Committee Pack", "aigc": "AI Governance Committee Pack"}
    main = packs["mrmc"] if report_type in ("executive", "mrmc") else packs[report_type]
    header(story, institution, titles[report_type],
           "Prepared from platform records. All data is synthetic and the institution is fictional.",
           report_id, main["as_of"], prepared_by)
    if report_type == "executive":
        story.append(Paragraph("Executive summary", H2))
        for code in ("mrmc", "fcmoc", "aigc"):
            story.append(Paragraph(f"<b>{esc(packs[code]['title'])}.</b> {esc(packs[code]['summary'])}", BODY))
            story.append(Spacer(1, 3))
        sec_kris(story, main["kpis"])
        sec_trend_charts(story, trends)
        sec_inventory_changes(story, packs["mrmc"]["inventory_changes"])
        sec_validation_outcomes(story, packs["mrmc"]["validation_outcomes"], packs["mrmc"]["validation_pipeline"])
        sec_findings(story, packs["mrmc"]["findings"])
        sec_monitoring(story, packs["fcmoc"]["monitoring"])
        sec_ai(story, packs["aigc"])
        recs, seen = [], set()
        for code in ("mrmc", "fcmoc", "aigc"):
            for r in packs[code]["recommendations"]:
                key = " ".join(r.split()[:3])
                if key not in seen and r != "No escalations required this period.":
                    seen.add(key)
                    recs.append(r)
        sec_recommendations(story, recs or ["No escalations required this period."])
    elif report_type == "mrmc":
        sec_summary(story, main)
        sec_kris(story, main["kpis"])
        sec_trend_charts(story, trends)
        sec_inventory_changes(story, main["inventory_changes"])
        sec_validation_outcomes(story, main["validation_outcomes"], main["validation_pipeline"])
        sec_findings(story, main["findings"])
        story.append(Paragraph("Inventory", H2))
        rows = [["Model", "Name", "Risk", "SR 26-2 classification", "Approval", "Next validation", "Docs"]] + [
            [m["model_id"], m["name"], m["risk_rating"], m["classification"], m["approval"], m["next_validation"],
             m["documentation"]] for m in main["inventory"]]
        story.append(table(rows, [0.9, 1.7, 0.5, 1.6, 1.0, 0.8, 0.7]))
        sec_ai(story, packs["aigc"])
        sec_recommendations(story, main["recommendations"])
    elif report_type == "fcmoc":
        sec_summary(story, main)
        sec_kris(story, main["kpis"])
        sec_monitoring(story, main["monitoring"])
        ps = trends["periods"]
        story.append(Spacer(1, 4))
        story.append(bar_chart([p["period"][2:] for p in ps], [[p["alerts"] for p in ps],
                                                                [p["alerts_escalated"] for p in ps]],
                               ["Alerts", "Escalated"], "Alert volume and escalations by period"))
        sec_trend_charts(story, trends)
        sec_findings(story, main["findings"])
        sec_controls(story, main["part504_controls"], "3 NYCRR Part 504 controls")
        sec_recommendations(story, main["recommendations"])
    else:
        sec_summary(story, main)
        sec_ai(story, main)
        if main["assessments_awaiting_review"]:
            story.append(Paragraph("Assessments awaiting review", H2))
            rows = [["Assessment", "System", "Derived classification", "Readiness", "Gaps"]] + [
                [a["assessment_id"], a["system_id"], a["classification"], f"{a['readiness']}%", a["gaps"]]
                for a in main["assessments_awaiting_review"]]
            story.append(table(rows, [1.1, 0.8, 2.6, 1.0, 0.8]))
        if main["bias_tests"]:
            story.append(Paragraph("Outcome disparity tests", H2))
            rows = [["System", "Periods", "Records", "Min impact ratio", "Min FPR ratio", "Result"]] + [
                [b["system_id"], b["periods"], f"{b['records']:,}", esc(b["min_impact_ratio"]),
                 esc(b["min_fpr_ratio"]), "Pass" if b["passed"] else "Fail"] for b in main["bias_tests"]]
            story.append(table(rows, [0.8, 1.4, 0.9, 1.3, 1.3, 0.8], status_col=5))
        sec_controls(story, main["ai_controls"], "AI governance controls")
        sec_recommendations(story, main["recommendations"])
    sec_disclaimer(story, main["disclaimer"])
    return build(titles[report_type], f"{institution} | {report_id} | Synthetic data. Not a certification of "
                                      f"regulatory compliance.", story)


def render_validation(report_id: str, v: Dict[str, Any], institution: str, prepared_by: str) -> bytes:
    story: List = []
    header(story, institution, f"Validation Report {v['validation_id']}",
           f"{v['model']['model_id']} {v['model']['name']} | {v['validation_type']} validation | status {v['status']}",
           report_id, v["as_of"], prepared_by)
    story.append(Paragraph("Conclusion", H2))
    story.append(Paragraph(f"<b>Overall rating:</b> {esc(v['overall_rating'] or 'Not yet rated')}", BODY))
    story.append(Paragraph(esc(v["summary"] or "Fieldwork in progress."), BODY))
    if v["conditions"]:
        story.append(Paragraph(f"<b>Conditions of approval:</b> {esc(v['conditions'])}", BODY))
    story.append(Paragraph("Scope and team", H2))
    rows = [["Item", "Detail"], ["Scope areas", ", ".join(v["scope_areas"])], ["Scope notes", v["scope_notes"] or "-"],
            ["Lead validator", v["lead_validator"]["full_name"] if v["lead_validator"] else "Not assigned"],
            ["Team", ", ".join(t["full_name"] for t in v["team"]) or "-"],
            ["Independence", ("Attested: " + v["independence_statement"]) if v["independence_attested"] else "Not yet attested"],
            ["Schedule", f"{esc(v['scheduled_start'])} to {esc(v['scheduled_end'])}"],
            ["Submitted / decided", f"{esc(v['submitted_on'])} / {esc(v['decided_on'])}"]]
    story.append(table(rows, [1.6, 5.5]))
    story.append(Paragraph("Model under review", H2))
    m = v["model_detail"]
    rows = [["Item", "Detail"], ["Methodology", m["methodology"]], ["Risk rating", m["risk_rating"]],
            ["SR 26-2 classification", m["supervisory_classification"]], ["Known limitations", m["limitations"]]]
    story.append(table(rows, [1.6, 5.5]))
    if v.get("monitoring"):
        block = [Paragraph("Outcomes analysis (monitoring results)", H2)]
        rec = v["monitoring"].get("recall") or []
        prec = v["monitoring"].get("precision") or []
        labels = [p["period"] for p in (rec or prec)]
        series = {}
        if rec:
            series["Recall"] = [p["value"] for p in rec]
        if prec:
            series["Precision"] = [p["value"] for p in prec]
        if series:
            lim = rec[-1]["breach_limit"] if rec and rec[-1].get("breach_limit") is not None else None
            block.append(line_chart(labels, series, "Monthly recall and precision (dashed line: recall breach limit)", lim))
        story.append(KeepTogether(block))
    story.append(Paragraph("Findings", H2))
    if v["findings"]:
        rows = [["Finding", "Severity", "Title", "Status", "Target"]] + [
            [f["finding_id"], f["severity"], f["title"], f["status"], f["target_date"]] for f in v["findings"]]
        story.append(table(rows, [1.0, 0.7, 3.3, 1.2, 0.9], status_col=1))
    else:
        story.append(Paragraph("No findings raised.", MUTE))
    story.append(Paragraph("Evidence", H2))
    if v["evidence"]:
        rows = [["Evidence", "Title", "Type", "File", "SHA-256 (first 16)"]] + [
            [e["evidence_id"], e["title"], e["evidence_type"], e["file_name"] or "-", (e["sha256"] or "-")[:16]]
            for e in v["evidence"]]
        story.append(table(rows, [0.9, 2.0, 1.2, 1.6, 1.4]))
    else:
        story.append(Paragraph("No evidence attached yet.", MUTE))
    if v["approvals"]:
        story.append(Paragraph("Approval record", H2))
        rows = [["Approver", "Decision", "Date", "Comments"]] + [
            [a["approver"]["full_name"], a["decision"], a["decided_at"], a["comments"]] for a in v["approvals"]]
        story.append(table(rows, [1.5, 1.4, 1.0, 3.2]))
    story.append(Paragraph("Workflow history", H2))
    rows = [["Date", "Event", "From", "To", "By"]] + [
        [h["occurred_at"], h["event_type"].replace("_", " ").title(), h["from_status"] or "-", h["to_status"] or "-",
         h["actor"]["full_name"]] for h in v["history"]]
    story.append(table(rows, [1.0, 1.4, 1.4, 1.4, 1.9]))
    sec_disclaimer(story, "Generated by ModelGuard from synthetic data for a fictional bank.")
    return build(f"Validation Report {v['validation_id']}",
                 f"{institution} | {report_id} | Synthetic data. Not a certification of regulatory compliance.", story)
