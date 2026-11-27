"""Module E: executive KPIs, historical trends and committee packs.

Every figure comes from a query over the platform's records. Narrative text (executive summary and
recommendations) is assembled from those figures by fixed rules, so the same data always produces the
same wording and every sentence can be traced to a number.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import FINDING_OPEN_STATUSES, SEVERITY_ORDER
from app.models.ai import AIAssessment, AISystem, BiasTestResult, LLMEvalRun
from app.models.audit import AuditEvent
from app.models.data import Alert, SimulationPeriod
from app.models.inventory import InventoryModel
from app.models.monitoring import Breach, FeatureDrift, MetricResult, MonitoringRun
from app.models.regulatory import Control
from app.models.validation import Finding, Validation, WorkflowEvent
from app.services import monitoring as mon
from app.services import regulatory as reg
from app.services.inventory import documentation_completeness
from app.simulation.world import period_bounds

COMMITTEES = {
    "mrmc": "Model Risk Management Committee",
    "fcmoc": "Financial Crime Model Oversight Committee",
    "aigc": "AI Governance Committee",
}
FINCRIME = ["MDL-TM-001", "MDL-SAD-007", "MDL-SF-002", "MDL-NS-003", "MDL-PEP-005", "MDL-AM-006", "MDL-CRS-004",
            "MDL-COR-010"]
ACTIVE_VAL = ["Not Started", "Scheduled", "In Progress", "Pending Review"]


def _models(db: Session) -> List[InventoryModel]:
    return list(db.execute(select(InventoryModel).where(InventoryModel.is_archived.is_(False))
                           .order_by(InventoryModel.model_id)).unique().scalars())


def models_in_breach(db: Session) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    latest = mon.latest_runs(db)
    for mid, run in latest.items():
        if run.overall_status != "Breach":
            continue
        m = db.get(InventoryModel, mid)
        bs = list(db.execute(select(Breach).where(Breach.run_id == run.id, Breach.level == "Breach")).scalars())
        worst = max(bs, key=lambda b: SEVERITY_ORDER.get(b.severity, 0)) if bs else None
        out[m.model_id] = {"model_id": m.model_id, "name": m.name, "period": run.period, "source": "monitoring",
                           "metrics": [{"metric": b.metric, "value": b.value, "severity": b.severity,
                                        "consecutive_periods": b.consecutive_periods} for b in bs],
                           "worst_severity": worst.severity if worst else None}
    for s in db.execute(select(AISystem).where(AISystem.linked_model_id.isnot(None))).unique().scalars():
        ev = db.execute(select(LLMEvalRun).where(LLMEvalRun.ai_system_id == s.id)
                        .order_by(LLMEvalRun.run_at.desc(), LLMEvalRun.id.desc())).unique().scalars().first()
        if ev and not ev.passed and s.linked_model.model_id not in out:
            out[s.linked_model.model_id] = {
                "model_id": s.linked_model.model_id, "name": s.linked_model.name, "period": ev.run_at.date().isoformat(),
                "source": f"LLM evaluation {ev.run_id}", "worst_severity": "High",
                "metrics": [{"metric": t["metric"], "value": t["value"], "severity": "Breach", "consecutive_periods": 1}
                            for t in ev.threshold_results if t["status"] == "Breach"]}
    return out


def executive_kpis(db: Session, today: date) -> Dict[str, Any]:
    models = _models(db)
    active_vals = list(db.execute(select(Validation).where(Validation.status.in_(ACTIVE_VAL))).unique().scalars())
    findings = list(db.execute(select(Finding)).unique().scalars())
    open_f = [f for f in findings if f.status in FINDING_OPEN_STATUSES]
    breach = models_in_breach(db)
    ai = list(db.execute(select(AISystem)).unique().scalars())
    completeness = [documentation_completeness(m.documentation_checklist or {}) for m in models]
    open_breaches = mon.open_breach_counts(db)
    sev_totals: Dict[str, int] = {}
    for c in open_breaches.values():
        for k, v in c.items():
            sev_totals[k] = sev_totals.get(k, 0) + v
    return {
        "as_of": today.isoformat(),
        "total_models": len(models),
        "high_risk_models": sum(1 for m in models if m.risk_rating == "High"),
        "models_awaiting_validation": len({v.model_id for v in active_vals}),
        "overdue_validations": sum(1 for m in models if m.next_validation_date and m.next_validation_date < today),
        "validations_due_90_days": sum(1 for m in models if m.next_validation_date and
                                       today <= m.next_validation_date <= today + timedelta(days=90)),
        "open_critical_findings": sum(1 for f in open_f if f.severity == "Critical"),
        "open_high_findings": sum(1 for f in open_f if f.severity == "High"),
        "outstanding_remediation_actions": len(open_f),
        "overdue_remediation_actions": sum(1 for f in open_f if f.target_date and f.target_date < today),
        "models_breaching_thresholds": len(breach),
        "open_breaches_by_severity": sev_totals,
        "ai_systems_total": len(ai),
        "ai_systems_awaiting_approval": sum(1 for s in ai if s.approval_status in ("Draft", "Under Review")),
        "documentation_completeness_pct": round(100 * sum(completeness) / len(completeness), 1) if completeness else None,
        "documentation_complete_models": sum(1 for m in models if m.documentation_status == "Complete"),
        "approval_status_counts": _count([m.approval_status for m in models]),
        "risk_rating_counts": _count([m.risk_rating for m in models]),
        "classification_counts": _count([m.supervisory_classification for m in models]),
    }


def _count(values: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _risk_accepted_on(db: Session) -> Dict[int, date]:
    rows = db.execute(select(WorkflowEvent.entity_id, WorkflowEvent.occurred_at).where(
        WorkflowEvent.entity_type == "finding", WorkflowEvent.to_status == "Risk Accepted")).all()
    return {eid: (dt.date() if isinstance(dt, datetime) else dt) for eid, dt in rows}


def trends(db: Session) -> Dict[str, Any]:
    periods = list(db.execute(select(SimulationPeriod).order_by(SimulationPeriod.period)).scalars())
    runs = list(db.execute(select(MonitoringRun).where(MonitoringRun.is_latest.is_(True))).scalars())
    by_period: Dict[str, List[MonitoringRun]] = {}
    for r in runs:
        by_period.setdefault(r.period, []).append(r)
    breaches = db.execute(select(Breach.period, Breach.severity, func.count()).join(
        MonitoringRun, Breach.run_id == MonitoringRun.id).where(MonitoringRun.is_latest.is_(True),
                                                                Breach.level == "Breach")
        .group_by(Breach.period, Breach.severity)).all()
    alerts = dict(db.execute(select(Alert.period, func.count()).group_by(Alert.period)).all())
    escalated = dict(db.execute(select(Alert.period, func.count()).where(Alert.escalated.is_(True))
                                .group_by(Alert.period)).all())
    findings = list(db.execute(select(Finding)).unique().scalars())
    accepted = _risk_accepted_on(db)
    out = []
    for p in periods:
        _, end = period_bounds(p.period)
        open_f = [f for f in findings if f.raised_on <= end and not (f.closed_on and f.closed_on <= end)
                  and not (f.id in accepted and accepted[f.id] <= end)]
        rs = by_period.get(p.period, [])
        sev = {s: n for per, s, n in breaches if per == p.period}
        out.append({
            "period": p.period, "scenario": p.scenario, "drift_intensity": p.drift_intensity,
            "is_reference": p.is_reference,
            "models_monitored": len(rs), "models_in_breach": sum(1 for r in rs if r.overall_status == "Breach"),
            "models_in_warning": sum(1 for r in rs if r.overall_status == "Warning"),
            "breaches": sum(sev.values()), "breaches_by_severity": sev,
            "alerts": alerts.get(p.period, 0), "alerts_escalated": escalated.get(p.period, 0),
            "open_findings": len(open_f),
            "open_findings_overdue": sum(1 for f in open_f if f.target_date and f.target_date < end),
        })
    val_q: Dict[str, Dict[str, int]] = {}
    for v in db.execute(select(Validation).where(Validation.decided_on.isnot(None))).unique().scalars():
        q = f"{v.decided_on.year} Q{(v.decided_on.month - 1) // 3 + 1}"
        val_q.setdefault(q, {})
        val_q[q][v.status] = val_q[q].get(v.status, 0) + 1
    return {"periods": out, "validation_outcomes_by_quarter": dict(sorted(val_q.items()))}


def _latest_metrics(db: Session, model_ids: List[str]) -> List[Dict[str, Any]]:
    latest = mon.latest_runs(db)
    rows = []
    for m in _models(db):
        if m.model_id not in model_ids or m.id not in latest:
            continue
        r = latest[m.id]
        mets = {x.metric: x for x in db.execute(select(MetricResult).where(MetricResult.run_id == r.id)).scalars()}
        drift = db.execute(select(FeatureDrift).where(FeatureDrift.run_id == r.id, FeatureDrift.drift_flag.is_(True))
                           .order_by(FeatureDrift.psi.desc())).scalars().all()
        alerts = db.execute(select(func.count()).select_from(Alert).where(Alert.model_id == m.id,
                                                                          Alert.period == r.period)).scalar()
        rows.append({
            "model_id": m.model_id, "name": m.name, "risk_rating": m.risk_rating, "period": r.period,
            "status": r.overall_status, "records": r.record_count, "alerts": alerts,
            "alerting": bool(mon.PROFILES.get(m.model_id, {}).get("conversion")),
            "metrics": {k: {"value": v.value, "status": v.status, "warning": v.warning_limit, "breach": v.breach_limit}
                        for k, v in mets.items()},
            "drifting_features": [{"feature": d.feature, "psi": d.psi, "level": d.drift_level} for d in drift],
        })
    return rows


def _audit_changes(db: Session, since: datetime, actions_prefix: List[str]) -> List[Dict[str, Any]]:
    rows = db.execute(select(AuditEvent).where(AuditEvent.occurred_at >= since).order_by(AuditEvent.id.desc())
                      .limit(400)).scalars()
    return [{"occurred_at": e.occurred_at, "actor": e.actor_username, "action": e.action, "entity": e.entity_ref,
             "summary": e.summary} for e in rows if any(e.action.startswith(p) for p in actions_prefix)
            and e.actor_username != "system"]


def _findings_block(db: Session, today: date, model_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    fs = [f for f in db.execute(select(Finding)).unique().scalars()
          if model_ids is None or f.model.model_id in model_ids]
    open_f = [f for f in fs if f.status in FINDING_OPEN_STATUSES]

    def line(f):
        return {"finding_id": f.finding_id, "model_id": f.model.model_id, "title": f.title, "severity": f.severity,
                "status": f.status, "owner": f.remediation_owner.full_name if f.remediation_owner else "",
                "target_date": f.target_date, "overdue_days": max(0, (today - f.target_date).days) if f.target_date else 0,
                "extensions": f.extension_count}
    status_counts = _count([f.status for f in fs])
    return {
        "total": len(fs), "open": len(open_f), "status_counts": status_counts,
        "severity_open": _count([f.severity for f in open_f]),
        "critical_and_high_open": [line(f) for f in sorted(open_f, key=lambda f: (-SEVERITY_ORDER[f.severity], f.finding_id))
                                   if f.severity in ("Critical", "High")],
        "overdue": [line(f) for f in open_f if f.target_date and f.target_date < today],
        "closed_last_180_days": sum(1 for f in fs if f.closed_on and (today - f.closed_on).days <= 180),
    }


def _recommendations(k: Dict[str, Any], breach: Dict[str, Dict], findings: Dict[str, Any], extra: List[str]) -> List[str]:
    recs = []
    if k.get("overdue_validations"):
        recs.append(f"Prioritise revalidation: {k['overdue_validations']} inventory entr"
                    f"{'y is' if k['overdue_validations'] == 1 else 'ies are'} past the policy revalidation date.")
    crit = [f for f in findings["critical_and_high_open"] if f["severity"] == "Critical"]
    if crit:
        ids = ", ".join(f["finding_id"] for f in crit)
        overdue = sum(1 for f in crit if f["overdue_days"] > 0)
        recs.append(f"Hold remediation owners to dates for Critical finding(s) {ids}"
                    + (f"; {overdue} already past target." if overdue else "."))
    perf = {"precision", "recall", "f1", "false_positive_rate", "alert_conversion_rate", "override_rate",
            "factual_accuracy", "hallucination_rate", "unsupported_claim_rate", "policy_compliance",
            "response_consistency"}

    def persistent(b, kinds):
        return any(x.get("consecutive_periods", 1) >= 2 and x["metric"] in kinds for x in b["metrics"])
    perf_p = [b["model_id"] for b in breach.values() if persistent(b, perf)]
    dq_p = [b["model_id"] for b in breach.values() if persistent(b, {"dq_exception_rate"})]
    drift_p = [b["model_id"] for b in breach.values() if persistent(b, {"psi", "max_feature_psi"})]
    if perf_p:
        recs.append("Require recalibration or tuning plans for " + ", ".join(perf_p)
                    + ", where a performance breach has persisted for two or more periods.")
    if dq_p:
        recs.append("Require a data remediation plan for " + ", ".join(dq_p)
                    + ", where input data quality has breached limits for two or more periods.")
    if drift_p:
        recs.append("Review population drift on " + ", ".join(drift_p) + " before the next monitoring cycle.")
    covered = set(perf_p) | set(dq_p) | set(drift_p)
    other = [b["model_id"] for b in breach.values() if b["model_id"] not in covered]
    if other:
        recs.append("Review root-cause analysis for new threshold breaches on " + ", ".join(other) + ".")
    recs.extend(extra)
    if not recs:
        recs.append("No escalations required this period.")
    return recs


def committee_pack(db: Session, code: str, today: date) -> Dict[str, Any]:
    if code not in COMMITTEES:
        raise ValueError(code)
    k = executive_kpis(db, today)
    breach = models_in_breach(db)
    since = datetime.now(timezone.utc) - timedelta(days=90)
    pack: Dict[str, Any] = {"committee": code, "title": COMMITTEES[code], "as_of": today.isoformat(), "kpis": k}
    models = _models(db)

    if code == "mrmc":
        findings = _findings_block(db, today)
        vals = list(db.execute(select(Validation).order_by(Validation.validation_id)).unique().scalars())
        decided = [v for v in vals if v.decided_on and (today - v.decided_on).days <= 365]
        pack.update({
            "inventory": [{"model_id": m.model_id, "name": m.name, "risk_rating": m.risk_rating,
                           "classification": m.supervisory_classification, "lifecycle": m.lifecycle_stage,
                           "approval": m.approval_status, "next_validation": m.next_validation_date,
                           "documentation": m.documentation_status} for m in models],
            "inventory_changes": _audit_changes(db, since, ["MODEL_"]),
            "validation_outcomes": [{"validation_id": v.validation_id, "model_id": v.model.model_id,
                                     "type": v.validation_type, "status": v.status, "rating": v.overall_rating,
                                     "decided_on": v.decided_on, "conditions": v.conditions,
                                     "reason": (v.approvals[-1].comments if v.status == "Rejected" and v.approvals
                                                else "")} for v in decided],
            "validation_pipeline": [{"validation_id": v.validation_id, "model_id": v.model.model_id,
                                     "status": v.status, "lead": v.lead_validator.full_name if v.lead_validator else "",
                                     "scheduled_end": v.scheduled_end} for v in vals if v.status in ACTIVE_VAL],
            "findings": findings,
        })
        extra = []
        incomplete = [m.model_id for m in models if m.risk_rating == "High" and m.documentation_status != "Complete"]
        if incomplete:
            extra.append(f"Close documentation gaps on High-risk entries {', '.join(incomplete)} before the next meeting.")
        pending = [v["validation_id"] for v in pack["validation_pipeline"] if v["status"] == "Pending Review"]
        if pending:
            extra.append(f"Decide on validation(s) awaiting approval: {', '.join(pending)}.")
        pack["recommendations"] = _recommendations(k, breach, findings, extra)
        pack["summary"] = (
            f"The inventory holds {k['total_models']} active entries, {k['high_risk_models']} rated High risk. "
            f"{k['models_awaiting_validation']} have a validation under way and {k['overdue_validations']} are past "
            f"their revalidation date. {findings['open']} findings are open, {k['open_critical_findings']} Critical, "
            f"and {k['overdue_remediation_actions']} are past target. {k['models_breaching_thresholds']} entries are "
            f"breaching monitoring or evaluation thresholds.")
    elif code == "fcmoc":
        rows = _latest_metrics(db, FINCRIME)
        findings = _findings_block(db, today, FINCRIME)
        ctrls = [reg.get_control(db, c) for c in ("CTL-10", "CTL-11", "CTL-12", "CTL-13")]
        pack.update({
            "monitoring": rows,
            "breaches": [b for b in breach.values() if b["model_id"] in FINCRIME],
            "findings": findings,
            "part504_controls": [{"control_id": c.control_id, "name": c.name, "status": c.implementation_status,
                                  "latest_test": (reg.latest_result(c).result if reg.latest_result(c) else "Manual"),
                                  "gaps": c.identified_gaps} for c in ctrls],
        })
        extra = []
        dq = [r["model_id"] for r in rows if r["metrics"].get("dq_exception_rate", {}).get("status") == "Breach"]
        if dq:
            extra.append(f"Escalate input data defects affecting {', '.join(dq)} to the data owners; data quality "
                         f"exceptions exceed the breach limit.")
        by_feature: Dict[str, List] = {}
        for r in rows:
            if r["drifting_features"]:
                f = r["drifting_features"][0]
                by_feature.setdefault(f["feature"], []).append((r["model_id"], f["psi"]))
        for feat, items in sorted(by_feature.items(), key=lambda kv: -max(p for _, p in kv[1]))[:3]:
            top = max(p for _, p in items)
            extra.append(f"Investigate input drift in '{feat}' (PSI up to {top:.2f}) affecting "
                         f"{', '.join(m for m, _ in items)}.")
        pack["recommendations"] = _recommendations({}, {k_: v for k_, v in breach.items() if k_ in FINCRIME},
                                                   findings, extra)
        in_breach = [b["model_id"] for b in pack["breaches"]]
        pack["summary"] = (
            f"{len(rows)} financial crime models were monitored for {rows[0]['period'] if rows else 'n/a'}. "
            f"{len(in_breach)} are in breach of at least one threshold"
            + (f" ({', '.join(in_breach)})" if in_breach else "") + ". "
            f"{findings['open']} findings on these models are open, {len(findings['overdue'])} past target.")
    else:
        systems = list(db.execute(select(AISystem).order_by(AISystem.system_id)).unique().scalars())
        pending = list(db.execute(select(AIAssessment).where(AIAssessment.status == "Submitted")).unique().scalars())
        evals = list(db.execute(select(LLMEvalRun).order_by(LLMEvalRun.run_at.desc())).unique().scalars())
        bias = list(db.execute(select(BiasTestResult).order_by(BiasTestResult.run_at.desc())).scalars())
        ctrls = [reg.get_control(db, c) for c in ("CTL-15", "CTL-16", "CTL-17", "CTL-18", "CTL-20", "CTL-21")]
        pending_cls = {a.ai_system_id: a.derived_classification for a in pending}

        def cls(s):
            if s.eu_ai_act_class == "Not assessed" and s.id in pending_cls:
                return f"Pending review: {pending_cls[s.id]}"
            return s.eu_ai_act_class
        pack.update({
            "systems": [{"system_id": s.system_id, "name": s.name, "classification": cls(s),
                         "approval": s.approval_status, "deployment": s.deployment_status, "tier": s.internal_risk_tier,
                         "oversight": s.human_oversight, "bias": s.bias_testing_status} for s in systems],
            "classification_counts": _count([s.eu_ai_act_class for s in systems]),
            "assessments_awaiting_review": [{"assessment_id": a.assessment_id, "system_id": a.ai_system.system_id,
                                             "classification": a.derived_classification, "readiness": a.overall_score,
                                             "gaps": len(a.gaps or [])} for a in pending],
            "evaluations": [{"run_id": e.run_id, "system_id": e.ai_system.system_id, "version": e.model_version,
                             "passed": e.passed, "metrics": e.metrics,
                             "breaches": [t["metric"] for t in e.threshold_results if t["status"] == "Breach"]}
                            for e in evals],
            "bias_tests": [{"system_id": next((s.system_id for s in systems if s.id == b.ai_system_id), ""),
                            "passed": b.passed, "min_impact_ratio": b.min_ratio, "min_fpr_ratio": b.min_fpr_ratio,
                            "periods": b.periods, "records": b.records} for b in bias],
            "ai_controls": [{"control_id": c.control_id, "name": c.name, "status": c.implementation_status,
                             "latest_test": (reg.latest_result(c).result if reg.latest_result(c) else "Manual"),
                             "gaps": c.identified_gaps} for c in ctrls],
        })
        recs = []
        if pending:
            recs.append("Review submitted readiness assessments: " + ", ".join(
                f"{a.assessment_id} ({a.ai_system.system_id})" for a in pending) + ".")
        hi = [s.system_id for s in systems if s.eu_ai_act_class.startswith("High-risk")
              or pending_cls.get(s.id, "").startswith("High-risk")]
        if hi:
            recs.append(f"Confirm a fundamental rights impact assessment plan for high-risk system(s) {', '.join(hi)} "
                        f"before Annex III obligations apply on 2 December 2027.")
        failing = {}
        for e in evals:
            failing.setdefault(e.ai_system.system_id, e)
        bad = [f"{sid} ({e.model_version})" for sid, e in failing.items() if not e.passed]
        if bad:
            recs.append(f"Do not promote versions whose latest evaluation breached thresholds: {', '.join(bad)}.")
        blocked = [s.system_id for s in systems if s.eu_ai_act_class.startswith("Prohibited")]
        if blocked:
            recs.append(f"Note that {', '.join(blocked)} was classified as a prohibited practice and is blocked.")
        planned = [c.control_id for c in ctrls if c.implementation_status in ("Planned", "Not implemented")]
        if planned:
            recs.append(f"Track delivery of AI controls not yet in place: {', '.join(planned)}.")
        pack["recommendations"] = recs or ["No escalations required this period."]
        pack["summary"] = (
            f"The AI inventory holds {len(systems)} systems: {k['ai_systems_awaiting_approval']} await approval, "
            f"{len(pending)} readiness assessment(s) await review, and {len(hi)} system(s) are classified or proposed "
            f"as high-risk under the bank's EU AI Act readiness assessment. {sum(1 for e in failing.values() if not e.passed)} "
            f"generative system(s) failed their latest evaluation run.")
    pack["disclaimer"] = ("Generated by ModelGuard from synthetic data for a fictional bank. Assessments and control "
                          "tests are internal governance tools and do not certify regulatory compliance.")
    return pack


def executive_dashboard(db: Session, today: date) -> Dict[str, Any]:
    k = executive_kpis(db, today)
    breach = models_in_breach(db)
    findings = _findings_block(db, today)
    upcoming = [{"model_id": m.model_id, "name": m.name, "risk_rating": m.risk_rating,
                 "next_validation_date": m.next_validation_date, "days": (m.next_validation_date - today).days}
                for m in _models(db) if m.next_validation_date and (m.next_validation_date - today).days <= 90]
    ai = [{"system_id": s.system_id, "name": s.name, "approval_status": s.approval_status,
           "classification": s.eu_ai_act_class}
          for s in db.execute(select(AISystem).where(AISystem.approval_status.in_(["Draft", "Under Review"]))
                              .order_by(AISystem.system_id)).unique().scalars()]
    cov = reg.requirement_coverage(db)
    ctrl = list(db.execute(select(Control)).unique().scalars())
    tests = [reg.latest_result(c) for c in ctrl if c.automated_test]
    return {"kpis": k, "models_in_breach": list(breach.values()),
            "critical_and_high_findings": findings["critical_and_high_open"], "overdue_findings": findings["overdue"],
            "upcoming_validations": sorted(upcoming, key=lambda x: x["days"]), "ai_awaiting_approval": ai,
            "controls": {"total": len(ctrl), "tests_total": len(tests),
                         "tests_passing": sum(1 for t in tests if t and t.result == "Pass"),
                         "requirements_with_gaps": sum(1 for r in cov if r["coverage"] in ("Gap", "Partially covered"))},
            "trends": trends(db)}
