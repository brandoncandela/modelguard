"""Module F: regulatory control mapping and automated control tests.

Each automated test reads live platform data and returns the population tested and the exceptions
found. A passing test is evidence that a control operated on this data; it is not a statement that the
bank complies with any regulation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import FINDING_OPEN_STATUSES
from app.core.errors import Forbidden, NotFound, WorkflowError
from app.models.ai import AIAssessment, AISystem, LLMEvalRun
from app.models.inventory import InventoryModel
from app.models.monitoring import Breach, MetricResult, MonitoringRun
from app.models.regulatory import Control, ControlTestResult, RegulatoryRequirement, RegulatorySource
from app.models.users import User
from app.models.validation import Finding, Validation
from app.services import audit
from app.services import monitoring as mon
from app.services.inventory import documentation_completeness

TestFn = Callable[[Session, date], Tuple[int, List[Dict[str, Any]], str]]


def _models(db: Session) -> List[InventoryModel]:
    return list(db.execute(select(InventoryModel).where(InventoryModel.is_archived.is_(False))).unique().scalars())


def t_inventory_completeness(db, today):
    exc = []
    models = _models(db)
    for m in models:
        missing = [f for f in ("limitations", "risk_rationale", "classification_rationale", "methodology")
                   if not (getattr(m, f) or "").strip()]
        if not m.geographies:
            missing.append("geographies")
        if missing:
            exc.append({"item": m.model_id, "detail": f"Missing: {', '.join(missing)}"})
    return len(models), exc, "Mandatory inventory fields populated for every active entry"


def t_documentation_currency(db, today):
    models = [m for m in _models(db) if m.risk_rating == "High"]
    exc = [{"item": m.model_id, "detail": f"{m.documentation_status} ({documentation_completeness(m.documentation_checklist or {}) * 100:.0f}% of artifacts)"}
           for m in models if m.documentation_status != "Complete"]
    return len(models), exc, "High-risk entries have complete, current documentation"


def t_validation_before_use(db, today):
    models = [m for m in _models(db) if m.lifecycle_stage == "Production"]
    exc = [{"item": m.model_id, "detail": f"In production with approval status '{m.approval_status}'"}
           for m in models if m.approval_status not in ("Approved", "Conditionally Approved")]
    return len(models), exc, "Production entries hold a current approval from independent validation"


def t_revalidation_cycle(db, today):
    models = [m for m in _models(db) if m.lifecycle_stage != "Retired"]
    exc = [{"item": m.model_id, "detail": f"Next validation was due {m.next_validation_date}"}
           for m in models if m.next_validation_date and m.next_validation_date < today]
    return len(models), exc, "No entry is past its policy revalidation date"


def t_validator_independence(db, today):
    vs = list(db.execute(select(Validation)).unique().scalars())
    exc = []
    for v in vs:
        team = [int(x) for x in (v.team or [])] + ([v.lead_validator_id] if v.lead_validator_id else [])
        if set(team) & {v.model.business_owner_id, v.model.model_risk_owner_id}:
            exc.append({"item": v.validation_id, "detail": "Validator is also an owner of the model"})
        if v.status not in ("Not Started", "Scheduled") and not v.independence_attested:
            exc.append({"item": v.validation_id, "detail": "Fieldwork started without independence attestation"})
        for a in v.approvals:
            if a.approver_id in team:
                exc.append({"item": v.validation_id, "detail": "Approver worked on the validation"})
    return len(vs), exc, "Validators and approvers are independent of the model and of each other"


def t_monitoring_coverage(db, today):
    latest_period = db.execute(select(func.max(MonitoringRun.period))).scalar()
    models = mon.monitored_models(db)
    exc = []
    for m in models:
        due = latest_period if m.monitoring_frequency == "Monthly" else max(
            p for p in mon.all_periods(db) if mon.is_due(m, p))
        has = db.execute(select(MonitoringRun.id).where(MonitoringRun.model_id == m.id, MonitoringRun.period == due,
                                                        MonitoringRun.is_latest.is_(True))).first()
        if not has:
            exc.append({"item": m.model_id, "detail": f"No monitoring run for {due}"})
    return len(models), exc, f"Every monitored entry has a run for its latest due period ({latest_period})"


def t_breach_escalation(db, today):
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = db.execute(select(Breach, InventoryModel.model_id).join(InventoryModel, Breach.model_id == InventoryModel.id)
                      .where(Breach.level == "Breach", Breach.severity.in_(["High", "Critical"]))).all()
    exc = []
    for b, mid in rows:
        detected = b.detected_at if b.detected_at.tzinfo else b.detected_at.replace(tzinfo=timezone.utc)
        if b.status == "Open" and detected < cutoff:
            exc.append({"item": b.breach_id, "detail": f"{mid} {b.metric} {b.severity} open more than 30 days"})
    return len(rows), exc, "High and Critical breaches acknowledged within 30 days"


def t_finding_timeliness(db, today):
    fs = list(db.execute(select(Finding).where(Finding.status.in_(FINDING_OPEN_STATUSES))).unique().scalars())
    exc = [{"item": f.finding_id, "detail": f"{f.severity} finding {(today - f.target_date).days} days past target"}
           for f in fs if f.target_date and f.target_date < today]
    return len(fs), exc, "Open findings are within their target dates"


def _latest_metric(db, model_id: str, metric: str):
    return db.execute(select(MetricResult, InventoryModel).join(InventoryModel, MetricResult.model_id == InventoryModel.id)
                      .join(MonitoringRun, MetricResult.run_id == MonitoringRun.id)
                      .where(InventoryModel.model_id == model_id, MetricResult.metric == metric,
                             MonitoringRun.is_latest.is_(True)).order_by(MetricResult.period.desc())).first()


def t_filtering_effectiveness(db, today):
    exc, n = [], 0
    for mid in ("MDL-SF-002", "MDL-NS-003", "MDL-PEP-005"):
        row = _latest_metric(db, mid, "recall")
        if row is None:
            continue
        n += 1
        r, _ = row
        if r.status == "Breach":
            exc.append({"item": mid, "detail": f"Recall {r.value:.3f} below breach limit {r.breach_limit} in {r.period}"})
    return n, exc, "Screening recall within tolerance in the latest period"


def t_tm_data_quality(db, today):
    exc, n = [], 0
    for mid in ("MDL-TM-001", "MDL-SAD-007", "MDL-SF-002"):
        row = _latest_metric(db, mid, "dq_exception_rate")
        if row is None:
            continue
        n += 1
        r, _ = row
        if r.status == "Breach":
            exc.append({"item": mid, "detail": f"Data quality exceptions {r.value * 100:.2f}% over limit "
                                               f"{r.breach_limit * 100:.1f}% in {r.period}"})
    return n, exc, "Transaction monitoring and filtering input data within quality limits"


def t_ai_assessment_coverage(db, today):
    systems = [s for s in db.execute(select(AISystem)).unique().scalars()
               if s.deployment_status in ("Production", "Pilot")]
    exc = []
    for s in systems:
        ok = db.execute(select(AIAssessment.id).where(AIAssessment.ai_system_id == s.id,
                                                      AIAssessment.status == "Approved")).first()
        if not ok:
            exc.append({"item": s.system_id, "detail": f"{s.deployment_status} without an approved assessment"})
    return len(systems), exc, "Deployed AI systems have an approved EU AI Act readiness assessment"


def t_prohibited_practice(db, today):
    systems = list(db.execute(select(AISystem)).unique().scalars())
    exc = [{"item": s.system_id, "detail": f"Classified prohibited but status {s.approval_status} / {s.deployment_status}"}
           for s in systems if s.eu_ai_act_class.startswith("Prohibited")
           and (s.approval_status != "Rejected" or s.deployment_status not in ("Blocked", "Not deployed"))]
    return len(systems), exc, "No system classified as a prohibited practice is approved or deployed"


def t_human_oversight(db, today):
    systems = [s for s in db.execute(select(AISystem)).unique().scalars()
               if s.affects_natural_persons and s.deployment_status in ("Production", "Pilot")]
    exc = [{"item": s.system_id, "detail": "No human oversight model defined"} for s in systems
           if s.human_oversight in ("", "None")]
    return len(systems), exc, "Deployed systems affecting people have a defined human oversight model"


def t_llm_evaluation_gate(db, today):
    systems = [s for s in db.execute(select(AISystem)).unique().scalars()
               if s.ai_technique.lower().startswith(("large language", "generative"))
               and s.deployment_status in ("Production", "Pilot")]
    exc = []
    for s in systems:
        ev = db.execute(select(LLMEvalRun).where(LLMEvalRun.ai_system_id == s.id)
                        .order_by(LLMEvalRun.run_at.desc(), LLMEvalRun.id.desc())).unique().scalars().first()
        if ev is None:
            exc.append({"item": s.system_id, "detail": "No evaluation run"})
        elif not ev.passed:
            exc.append({"item": s.system_id, "detail": f"Latest run {ev.run_id} ({ev.model_version}) breached thresholds"})
    return len(systems), exc, "Deployed generative systems passed their latest evaluation run"


def t_audit_chain(db, today):
    res = audit.verify_chain(db)
    exc = [{"item": str(b["id"]), "detail": "Hash chain break"} for b in res["breaks"]]
    return res["events_checked"], exc, "Audit trail hash chain verifies end to end"


TESTS: Dict[str, Tuple[str, TestFn]] = {
    "inventory_completeness": ("Inventory completeness", t_inventory_completeness),
    "documentation_currency": ("Documentation currency for high-risk entries", t_documentation_currency),
    "validation_before_use": ("Approval before production use", t_validation_before_use),
    "revalidation_cycle": ("Revalidation within policy cycle", t_revalidation_cycle),
    "validator_independence": ("Validator and approver independence", t_validator_independence),
    "monitoring_coverage": ("Monitoring coverage", t_monitoring_coverage),
    "breach_escalation": ("Breach acknowledgement within 30 days", t_breach_escalation),
    "finding_timeliness": ("Finding remediation timeliness", t_finding_timeliness),
    "filtering_effectiveness": ("Screening effectiveness", t_filtering_effectiveness),
    "tm_data_quality": ("Monitoring and filtering data quality", t_tm_data_quality),
    "ai_assessment_coverage": ("AI readiness assessment coverage", t_ai_assessment_coverage),
    "prohibited_practice_screen": ("Prohibited practice screen", t_prohibited_practice),
    "human_oversight_defined": ("Human oversight defined", t_human_oversight),
    "llm_evaluation_gate": ("LLM evaluation release gate", t_llm_evaluation_gate),
    "audit_chain_integrity": ("Audit trail integrity", t_audit_chain),
}


def run_tests(db: Session, actor: tuple, today: date, control_id: str = None) -> List[ControlTestResult]:
    stmt = select(Control).where(Control.automated_test.isnot(None))
    if control_id:
        stmt = stmt.where(Control.control_id == control_id)
    controls = list(db.execute(stmt.order_by(Control.control_id)).unique().scalars())
    if control_id and not controls:
        raise NotFound(f"Control {control_id} not found or has no automated test")
    out = []
    for c in controls:
        name, fn = TESTS[c.automated_test]
        population, exc, summary = fn(db, today)
        r = ControlTestResult(control_id=c.id, test_name=name, result="Pass" if not exc else "Fail",
                              population=population, exceptions=len(exc), exception_items=exc[:50],
                              summary=summary, run_by=actor[0])
        db.add(r)
        out.append(r)
    db.flush()
    failed = [c.control_id for c, r in zip(controls, out) if r.result == "Fail"]
    audit.record(db, actor[0], actor[1], "CONTROL_TESTS_RUN", "control", control_id or "all",
                 f"Ran {len(out)} automated control test(s): {len(failed)} with exceptions",
                 {"failed": failed})
    return out


EDITABLE_CONTROL = ["implementation_status", "last_reviewed_on", "next_review_on", "identified_gaps",
                    "remediation_actions", "evidence_requirement", "owner_id", "description"]


def update_control(db: Session, user: User, c: Control, changes: Dict[str, Any]) -> Control:
    if user.role not in ("admin", "compliance_reviewer"):
        raise Forbidden("Controls are maintained by compliance reviewers or administrators")
    if "owner_id" in changes and db.get(User, changes["owner_id"]) is None:
        raise WorkflowError("Control owner not found")
    if "implementation_status" in changes and changes["implementation_status"] not in (
            "Implemented", "Partially implemented", "Not implemented", "Planned"):
        raise WorkflowError("Unknown implementation status")
    before = {k: getattr(c, k) for k in changes if k in EDITABLE_CONTROL}
    for k in before:
        setattr(c, k, changes[k])
    delta = audit.diff(before, {k: getattr(c, k) for k in before})
    if delta:
        audit.record(db, user.username, user.role, "CONTROL_UPDATED", "control", c.control_id,
                     f"Updated {', '.join(sorted(delta))}", delta)
    return c


def latest_result(c: Control):
    return c.test_results[0] if c.test_results else None


def requirement_coverage(db: Session) -> List[Dict[str, Any]]:
    """Coverage of each requirement by its mapped controls. Superseded sources are shown as historical."""
    rows = []
    for r in db.execute(select(RegulatoryRequirement).order_by(RegulatoryRequirement.requirement_id)).unique().scalars():
        historical = r.source.status in ("Superseded", "Rescinded")
        states = []
        for c in r.controls:
            t = latest_result(c)
            ok = c.implementation_status == "Implemented" and (t is None or t.result == "Pass")
            partial = c.implementation_status in ("Implemented", "Partially implemented")
            states.append("ok" if ok else ("partial" if partial else "gap"))
        if historical:
            cov = "Historical reference"
        elif not states:
            cov = "No control mapped"
        elif all(s == "ok" for s in states):
            cov = "Covered"
        elif any(s in ("ok", "partial") for s in states):
            cov = "Partially covered"
        else:
            cov = "Gap"
        rows.append({"requirement_id": r.requirement_id, "source": r.source.short_name,
                     "source_status": r.source.status, "obligation_type": r.obligation_type, "section": r.section,
                     "theme": r.theme, "summary": r.summary, "controls": [c.control_id for c in r.controls],
                     "coverage": cov})
    return rows


def get_control(db: Session, control_id: str) -> Control:
    c = db.execute(select(Control).where(Control.control_id == control_id)).unique().scalar_one_or_none()
    if c is None:
        raise NotFound(f"Control {control_id} not found")
    return c


def sources(db: Session) -> List[RegulatorySource]:
    return list(db.execute(select(RegulatorySource).order_by(RegulatorySource.source_id)).unique().scalars())
