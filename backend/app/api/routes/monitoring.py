from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import breaches as br_doc
from app.analytics import drift as drift_doc
from app.analytics import psi as psi_doc
from app.api.deps import require
from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.models.data import Alert, SimulationPeriod, SystemSetting
from app.models.inventory import InventoryModel
from app.models.monitoring import Breach, FeatureDrift, MetricResult, MonitoringRun
from app.models.users import User
from app.services import inventory as inv
from app.services import monitoring as svc
from app.services import simulation
from app.simulation import dq as dq_rules

router = APIRouter(tags=["monitoring"])

KEY_METRICS = ["precision", "recall", "f1", "false_positive_rate", "alert_conversion_rate", "override_rate", "psi",
               "max_feature_psi", "dq_exception_rate"]


def _metric_dict(r: MetricResult, with_details: bool = False) -> dict:
    d = {"metric": r.metric, "value": r.value, "numerator": r.numerator, "denominator": r.denominator,
         "status": r.status, "warning_limit": r.warning_limit, "breach_limit": r.breach_limit,
         "direction": r.direction}
    if with_details:
        d["details"] = r.details
    return d


def _breach_dict(b: Breach, model: Optional[InventoryModel] = None) -> dict:
    d = {"breach_id": b.breach_id, "period": b.period, "metric": b.metric, "value": b.value,
         "warning_limit": b.warning_limit, "breach_limit": b.breach_limit, "direction": b.direction,
         "level": b.level, "severity": b.severity, "consecutive_periods": b.consecutive_periods,
         "severity_rationale": b.severity_rationale, "status": b.status, "detected_at": b.detected_at,
         "acknowledged_by": b.acknowledged_by, "acknowledged_at": b.acknowledged_at, "notes": b.notes}
    if model is not None:
        d.update(model_id=model.model_id, model_name=model.name, risk_rating=model.risk_rating)
    return d


@router.get("/monitoring/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    latest = svc.latest_runs(db)
    counts = svc.open_breach_counts(db)
    run_ids = [r.id for r in latest.values()]
    metrics = {}
    if run_ids:
        for r in db.execute(select(MetricResult).where(MetricResult.run_id.in_(run_ids))).scalars():
            metrics.setdefault(r.run_id, {})[r.metric] = _metric_dict(r)
    rows = []
    for m in db.execute(select(InventoryModel).where(InventoryModel.is_archived.is_(False))
                        .order_by(InventoryModel.model_id)).unique().scalars():
        run = latest.get(m.id)
        via = "scored_records" if m.model_id in svc.PROFILES else (
            "llm_evaluation" if m.methodology_type == "Large language model" else "none")
        rows.append({
            "model_id": m.model_id, "name": m.name, "category": m.category, "risk_rating": m.risk_rating,
            "monitoring_frequency": m.monitoring_frequency, "monitored_via": via,
            "latest_period": run.period if run else None, "run_id": run.run_id if run else None,
            "overall_status": run.overall_status if run else None, "record_count": run.record_count if run else None,
            "scenario": run.scenario if run else None,
            "metrics": {k: v for k, v in metrics.get(run.id, {}).items() if k in KEY_METRICS} if run else {},
            "open_breaches": counts.get(m.id, {}), "worst_open_severity": svc.worst_severity(counts.get(m.id, {})),
            "next_due": svc.next_due(m, run.period if run else None),
        })
    periods = [{"period": p.period, "scenario": p.scenario, "drift_intensity": p.drift_intensity,
                "is_reference": p.is_reference, "source": p.source}
               for p in db.execute(select(SimulationPeriod).order_by(SimulationPeriod.period)).scalars()]
    return {"models": rows, "periods": periods, "reference_periods": svc.reference_periods(db)}


@router.get("/monitoring/models/{model_id}/series")
def series(model_id: str, metrics: Optional[str] = Query(None, max_length=300), db: Session = Depends(get_db),
           _: User = Depends(require("monitoring:read"))):
    m = inv.get_model(db, model_id)
    wanted = [x.strip() for x in metrics.split(",")] if metrics else KEY_METRICS + ["alert_rate"]
    rows = db.execute(select(MetricResult, MonitoringRun.scenario).join(MonitoringRun, MetricResult.run_id == MonitoringRun.id)
                      .where(MetricResult.model_id == m.id, MonitoringRun.is_latest.is_(True),
                             MetricResult.metric.in_(wanted)).order_by(MetricResult.period)).all()
    out = {k: [] for k in wanted}
    for r, scenario in rows:
        out[r.metric].append({"period": r.period, "value": r.value, "status": r.status, "scenario": scenario,
                              "warning_limit": r.warning_limit, "breach_limit": r.breach_limit,
                              "numerator": r.numerator, "denominator": r.denominator})
    return {"model_id": m.model_id, "series": {k: v for k, v in out.items() if v},
            "reference_periods": svc.reference_periods(db)}


@router.get("/monitoring/models/{model_id}/runs")
def runs(model_id: str, db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    m = inv.get_model(db, model_id)
    rs = db.execute(select(MonitoringRun).where(MonitoringRun.model_id == m.id)
                    .order_by(MonitoringRun.period.desc(), MonitoringRun.id.desc())).scalars()
    return [{"run_id": r.run_id, "period": r.period, "overall_status": r.overall_status, "is_latest": r.is_latest,
             "record_count": r.record_count, "scenario": r.scenario, "triggered_by": r.triggered_by, "run_at": r.run_at}
            for r in rs]


@router.get("/monitoring/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    r = db.execute(select(MonitoringRun).where(MonitoringRun.run_id == run_id)).scalar_one_or_none()
    if r is None:
        raise NotFound(f"Run {run_id} not found")
    m = db.get(InventoryModel, r.model_id)
    mets = db.execute(select(MetricResult).where(MetricResult.run_id == r.id)).scalars()
    order = {k: i for i, k in enumerate(svc.METRIC_ORDER)}
    drift = db.execute(select(FeatureDrift).where(FeatureDrift.run_id == r.id).order_by(FeatureDrift.psi.desc())).scalars()
    bs = db.execute(select(Breach).where(Breach.run_id == r.id)).scalars()
    return {
        "run_id": r.run_id, "model_id": m.model_id, "model_name": m.name, "period": r.period,
        "reference": f"{r.reference_start} to {r.reference_end}", "record_count": r.record_count,
        "reference_count": r.reference_count, "scenario": r.scenario, "triggered_by": r.triggered_by,
        "run_at": r.run_at, "is_latest": r.is_latest, "overall_status": r.overall_status,
        "metrics": sorted([_metric_dict(x, True) for x in mets], key=lambda d: order.get(d["metric"], 99)),
        "drift": [{"feature": d.feature, "feature_type": d.feature_type, "psi": d.psi, "test": d.test_name,
                   "statistic": d.statistic, "p_value": d.p_value, "effect_size": d.effect_size,
                   "level": d.drift_level, "flag": d.drift_flag, "bins": d.details.get("bins", [])} for d in drift],
        "breaches": [_breach_dict(b) for b in bs],
    }


@router.get("/monitoring/models/{model_id}/distribution")
def distribution(model_id: str, period: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
                 db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    m = inv.get_model(db, model_id)
    stmt = select(MetricResult).join(MonitoringRun, MetricResult.run_id == MonitoringRun.id).where(
        MetricResult.model_id == m.id, MetricResult.metric == "psi", MonitoringRun.is_latest.is_(True))
    stmt = stmt.where(MetricResult.period == period) if period else stmt.order_by(MetricResult.period.desc())
    r = db.execute(stmt).scalars().first()
    if r is None:
        raise NotFound("No PSI result for that model and period")
    return {"model_id": m.model_id, "period": r.period, "psi": r.value, "band": r.details.get("band"),
            "bins": r.details.get("bins", []), "reference_n": r.details.get("reference_n"),
            "current_n": r.details.get("current_n")}


class ThresholdIn(BaseModel):
    metric: str = Field(max_length=40)
    warning_limit: float = Field(ge=-1e6, le=1e6)
    breach_limit: float = Field(ge=-1e6, le=1e6)
    rationale: str = Field(min_length=10, max_length=1000)
    is_active: bool = True


class ThresholdUpdate(BaseModel):
    items: List[ThresholdIn] = Field(min_length=1, max_length=30)


def _owner_or_admin(user: User, m: InventoryModel) -> None:
    if user.role == "model_owner" and not inv.can_edit(user, m):
        raise Forbidden("Model owners can only change monitoring settings for their own models")


@router.get("/monitoring/models/{model_id}/thresholds")
def get_thresholds(model_id: str, db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    m = inv.get_model(db, model_id)
    return [{"metric": t.metric, "kind": t.kind, "direction": t.direction, "warning_limit": t.warning_limit,
             "breach_limit": t.breach_limit, "rationale": t.rationale, "is_active": t.is_active,
             "updated_at": t.updated_at} for t in m.thresholds]


@router.put("/monitoring/models/{model_id}/thresholds")
def put_thresholds(model_id: str, body: ThresholdUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require("monitoring:configure"))):
    m = inv.get_model(db, model_id)
    _owner_or_admin(user, m)
    svc.set_thresholds(db, user, m, [i.model_dump() for i in body.items])
    db.commit()
    return get_thresholds(model_id, db, user)


class FrequencyIn(BaseModel):
    frequency: str = Field(pattern="^(Monthly|Quarterly)$")


@router.put("/monitoring/models/{model_id}/frequency")
def put_frequency(model_id: str, body: FrequencyIn, db: Session = Depends(get_db),
                  user: User = Depends(require("monitoring:configure"))):
    m = inv.get_model(db, model_id)
    _owner_or_admin(user, m)
    svc.set_frequency(db, user, m, body.frequency)
    db.commit()
    return {"model_id": m.model_id, "monitoring_frequency": m.monitoring_frequency}


class RunRequest(BaseModel):
    model_id: Optional[str] = Field(None, pattern=r"^MDL-[A-Z]{2,4}-\d{3}$")
    period: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")


@router.post("/monitoring/runs")
def trigger_run(body: RunRequest, db: Session = Depends(get_db), user: User = Depends(require("monitoring:run"))):
    period = body.period or db.execute(select(func.max(SimulationPeriod.period))).scalar()
    if body.model_id:
        m = inv.get_model(db, body.model_id)
        _owner_or_admin(user, m)
        runs = [svc.run_monitoring(db, m, period, (user.username, user.role))]
    else:
        if user.role == "model_owner":
            raise Forbidden("Model owners run monitoring for one of their models at a time")
        runs = svc.run_period(db, period, (user.username, user.role), respect_frequency=False)
    db.commit()
    return [{"run_id": r.run_id, "model_id": db.get(InventoryModel, r.model_id).model_id, "period": r.period,
             "overall_status": r.overall_status} for r in runs]


@router.get("/monitoring/breaches")
def list_breaches(status: Optional[List[str]] = Query(None), severity: Optional[List[str]] = Query(None),
                  level: Optional[str] = Query(None, pattern="^(Warning|Breach)$"),
                  model_id: Optional[str] = Query(None, max_length=32), period: Optional[str] = None,
                  page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    stmt = select(Breach, InventoryModel).join(InventoryModel, Breach.model_id == InventoryModel.id)
    if status:
        stmt = stmt.where(Breach.status.in_(status))
    if severity:
        stmt = stmt.where(Breach.severity.in_(severity))
    if level:
        stmt = stmt.where(Breach.level == level)
    if model_id:
        stmt = stmt.where(InventoryModel.model_id == model_id)
    if period:
        stmt = stmt.where(Breach.period == period)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(Breach.period.desc(), Breach.id.desc()).offset((page - 1) * page_size)
                      .limit(page_size)).unique().all()
    return {"items": [_breach_dict(b, m) for b, m in rows], "total": total, "page": page, "page_size": page_size}


class AckIn(BaseModel):
    notes: str = Field(min_length=5, max_length=1000)


@router.post("/monitoring/breaches/{breach_id}/acknowledge")
def acknowledge(breach_id: str, body: AckIn, db: Session = Depends(get_db),
                user: User = Depends(require("breach:acknowledge"))):
    b = svc.acknowledge_breach(db, user, breach_id, body.notes)
    db.commit()
    return _breach_dict(b, db.get(InventoryModel, b.model_id))


@router.post("/monitoring/breaches/{breach_id}/resolve")
def resolve(breach_id: str, body: AckIn, db: Session = Depends(get_db),
            user: User = Depends(require("breach:acknowledge"))):
    b = svc.acknowledge_breach(db, user, breach_id, body.notes, resolve=True)
    db.commit()
    return _breach_dict(b, db.get(InventoryModel, b.model_id))


class SimulateIn(BaseModel):
    scenario: str = Field(pattern="^(none|moderate|severe)$")


@router.post("/monitoring/simulate")
def simulate(body: SimulateIn, db: Session = Depends(get_db), user: User = Depends(require("monitoring:simulate"))):
    result = simulation.simulate_next(db, user, body.scenario)
    db.commit()
    return result


@router.delete("/monitoring/simulate")
def reset(db: Session = Depends(get_db), user: User = Depends(require("monitoring:simulate"))):
    result = simulation.reset_simulation(db, user)
    db.commit()
    return result


@router.get("/monitoring/alerts")
def alerts(model_id: Optional[str] = Query(None, max_length=32), period: Optional[str] = None,
           escalated: Optional[bool] = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
           db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    stmt = select(Alert, InventoryModel.model_id).join(InventoryModel, Alert.model_id == InventoryModel.id)
    if model_id:
        stmt = stmt.where(InventoryModel.model_id == model_id)
    if period:
        stmt = stmt.where(Alert.period == period)
    if escalated is not None:
        stmt = stmt.where(Alert.escalated.is_(escalated))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(Alert.created_on.desc(), Alert.alert_id).offset((page - 1) * page_size)
                      .limit(page_size)).all()
    return {"items": [{"alert_id": a.alert_id, "model_id": mid, "period": a.period, "created_on": a.created_on,
                       "subject_ref": a.subject_ref, "customer_id": a.customer_id, "score": a.score,
                       "rule_hits": a.rule_hits, "priority": a.priority, "disposition": a.disposition,
                       "escalated": a.escalated, "sar_filed": a.sar_filed} for a, mid in rows],
            "total": total, "page": page, "page_size": page_size}


@router.get("/monitoring/methodology")
def methodology(db: Session = Depends(get_db), _: User = Depends(require("monitoring:read"))):
    fitted = db.get(SystemSetting, "fitted_models")
    from app.simulation import detectors as det

    return {
        "metrics": svc.METRIC_DEFINITIONS,
        "psi": psi_doc.__doc__.strip(),
        "drift": drift_doc.__doc__.strip(),
        "severity": br_doc.__doc__.strip(),
        "data_quality_rules": dq_rules.rule_catalogue(),
        "feature_sources": {k: [{"feature": f, "type": t} for f, t in v] for k, v in svc.FEATURES.items()},
        "model_parameters": {
            "MDL-TM-001": {"rules": [{"code": c, "description": d, "weight": w} for c, d, w in det.TM_RULES],
                           "alert_threshold": det.TM_ALERT_THRESHOLD},
            "MDL-SF-002": {"similarity_threshold": det.SF_THRESHOLD},
            "MDL-NS-003": {"similarity_threshold": det.NS_THRESHOLD},
            "MDL-PEP-005": {"similarity_threshold": det.PEP_THRESHOLD},
            "MDL-CRS-004": {"high_cutoff": det.CRS_HIGH, "medium_cutoff": det.CRS_MEDIUM},
            **(fitted.value if fitted else {}),
        },
        "reference_periods": svc.reference_periods(db),
    }

