"""Module B: ongoing performance monitoring.

A monitoring run takes every record a model scored in one period, compares it with the reference
window, computes the metrics that apply to the model, tests input drift, checks thresholds and
records breaches with a severity. Nothing on the dashboard is typed in by hand; it all comes from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from app.analytics import breaches as br
from app.analytics import drift as dr
from app.analytics import metrics as mt
from app.analytics.psi import psi_band, psi_categorical, psi_numeric
from app.core.enums import BreachStatus, SEVERITY_ORDER
from app.core.errors import NotFound, WorkflowError
from app.models.data import ScoredRecord, SimulationPeriod, SystemSetting
from app.models.inventory import InventoryModel, ModelThreshold
from app.models.monitoring import Breach, FeatureDrift, MetricResult, MonitoringRun
from app.services import audit
from app.simulation.world import jurisdiction_tier

# Which metric families apply to each model, and where its input features come from
PROFILES: Dict[str, Dict[str, object]] = {
    "MDL-TM-001": {"conversion": True, "features": "transactions"},
    "MDL-SAD-007": {"conversion": True, "features": "transactions"},
    "MDL-SF-002": {"conversion": True, "features": "sf_payments"},
    "MDL-NS-003": {"conversion": True, "features": "applications"},
    "MDL-PEP-005": {"conversion": True, "features": "applications"},
    "MDL-AM-006": {"conversion": True, "features": "articles"},
    "MDL-CRS-004": {"conversion": False, "features": "customer_activity"},
    "MDL-COR-010": {"conversion": False, "features": "applications"},
    "MDL-AII-008": {"conversion": False, "override": True, "features": "triage"},
}

METRIC_ORDER = ["precision", "recall", "f1", "false_positive_rate", "alert_rate", "alert_conversion_rate",
                "override_rate", "psi", "max_feature_psi", "dq_exception_rate"]

FEATURES = {
    "transactions": [("amount_usd", "numeric"), ("channel", "categorical"), ("counterparty_tier", "categorical"),
                     ("direction", "categorical")],
    "sf_payments": [("amount_usd", "numeric"), ("channel", "categorical"), ("counterparty_tier", "categorical")],
    "applications": [("expected_monthly_volume", "numeric"), ("ownership_layers", "numeric"),
                     ("industry", "categorical"), ("segment", "categorical"), ("country_tier", "categorical")],
    "customer_activity": [("monthly_volume", "numeric"), ("cash_share", "numeric"), ("txn_count", "numeric")],
    "articles": [("word_count", "numeric")],
    "triage": [("source_model", "categorical")],
}

METRIC_DEFINITIONS = [
    {"metric": "precision", "name": "Precision", "formula": "TP / (TP + FP)",
     "meaning": "Share of alerts that were truly suspicious (or true list matches)."},
    {"metric": "recall", "name": "Recall (detection rate)", "formula": "TP / (TP + FN)",
     "meaning": "Share of truly suspicious records the model alerted. Production banks estimate this with "
                "below-the-line testing and look-backs; the synthetic data holds ground truth for every record."},
    {"metric": "f1", "name": "F1 score", "formula": "2 x precision x recall / (precision + recall)",
     "meaning": "Harmonic mean of precision and recall."},
    {"metric": "false_positive_rate", "name": "False-positive rate", "formula": "FP / (FP + TN)",
     "meaning": "Share of non-suspicious records that were alerted. The share of alerts that were false "
                "(FP / alerts), which AML teams often call the false positive rate, is reported alongside."},
    {"metric": "alert_rate", "name": "Alert rate", "formula": "alerts / records scored",
     "meaning": "Volume indicator for operational capacity."},
    {"metric": "alert_conversion_rate", "name": "Alert conversion rate", "formula": "alerts escalated to a case / alerts",
     "meaning": "Share of alerts investigators escalated. Based on recorded dispositions, not ground truth."},
    {"metric": "override_rate", "name": "Human override rate",
     "formula": "decisions differing from the recommendation / decisions",
     "meaning": "How often investigators disagreed with the AI triage recommendation."},
    {"metric": "psi", "name": "Population Stability Index (score)",
     "formula": "sum((a - e) x ln(a / e)) over reference-decile bins",
     "meaning": "Shift in the score distribution against the reference window. Under 0.10 stable, "
                "0.10 to 0.25 moderate, 0.25 or more significant. Scores with 20 or fewer distinct values "
                "(the rules engine) are binned by value instead of deciles."},
    {"metric": "max_feature_psi", "name": "Largest input feature PSI",
     "formula": "max over monitored input features of PSI",
     "meaning": "Input drift. Each feature is also tested with Kolmogorov-Smirnov (numeric) or chi-square "
                "(categorical) and flagged only when significant at 1% with a material effect size."},
    {"metric": "dq_exception_rate", "name": "Data quality exception rate",
     "formula": "records failing an input data quality rule / records",
     "meaning": "Missing or invalid inputs detected by rule checks before scoring."},
]


DISCRETE_SCORE_LEVELS = 20


def _score_label(v: float) -> str:
    return f"{v:g}"


def model_code(model: InventoryModel) -> str:
    return model.model_id


def world_settings(db: Session) -> dict:
    s = db.get(SystemSetting, "world_config")
    if s is None:
        raise WorkflowError("Synthetic world configuration missing; run the seed command")
    return s.value


def reference_periods(db: Session) -> List[str]:
    return list(world_settings(db)["reference_periods"])


def all_periods(db: Session) -> List[str]:
    return list(db.execute(select(SimulationPeriod.period).order_by(SimulationPeriod.period)).scalars())


# ---------------------------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------------------------


def _read(db: Session, stmt) -> pd.DataFrame:
    res = db.execute(stmt)
    return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


def load_scored(db: Session, model_pk: int, periods: List[str]) -> pd.DataFrame:
    stmt = select(ScoredRecord.period, ScoredRecord.record_ref, ScoredRecord.score, ScoredRecord.predicted,
                  ScoredRecord.actual, ScoredRecord.escalated, ScoredRecord.segment, ScoredRecord.dq_issue).where(
        ScoredRecord.model_id == model_pk, ScoredRecord.period.in_(periods))
    return _read(db, stmt)


def load_features(db: Session, source: str, model_pk: int, periods: List[str]) -> pd.DataFrame:
    from app.models.data import Application, MediaArticle, Transaction

    if source in ("transactions", "customer_activity"):
        df = _read(db, select(Transaction.period, Transaction.customer_id, Transaction.amount_usd, Transaction.channel,
                              Transaction.direction, Transaction.counterparty_country)
                   .where(Transaction.period.in_(periods)))
        if source == "transactions":
            df["counterparty_tier"] = df["counterparty_country"].map(jurisdiction_tier)
            return df
        df["amt"] = df["amount_usd"].fillna(0)
        df["cash_in"] = np.where(df["channel"] == "Cash deposit", df["amt"], 0.0)
        df["inflow"] = np.where(df["direction"] == "IN", df["amt"], 0.0)
        g = df.groupby(["period", "customer_id"]).agg(monthly_volume=("amt", "sum"), cash_in=("cash_in", "sum"),
                                                       inflow=("inflow", "sum"), txn_count=("amt", "size")).reset_index()
        g["cash_share"] = np.where(g["inflow"] > 0, g["cash_in"] / g["inflow"].replace(0, np.nan), 0.0)
        g["cash_share"] = g["cash_share"].fillna(0.0)
        return g
    if source == "sf_payments":
        df = _read(db, select(Transaction.period, Transaction.amount_usd, Transaction.channel,
                              Transaction.counterparty_country)
                   .join(ScoredRecord, and_(ScoredRecord.record_ref == Transaction.txn_id,
                                            ScoredRecord.model_id == model_pk))
                   .where(Transaction.period.in_(periods)))
        df["counterparty_tier"] = df["counterparty_country"].map(jurisdiction_tier)
        return df
    if source == "applications":
        df = _read(db, select(Application.period, Application.expected_monthly_volume, Application.ownership_layers,
                              Application.industry, Application.segment, Application.country)
                   .where(Application.period.in_(periods)))
        df["country_tier"] = df["country"].map(jurisdiction_tier)
        return df
    if source == "articles":
        df = _read(db, select(MediaArticle.period, MediaArticle.body).where(MediaArticle.period.in_(periods)))
        df["word_count"] = df["body"].fillna("").str.split().str.len()
        return df
    if source == "triage":
        df = load_scored(db, model_pk, periods)
        df["source_model"] = df["segment"]
        return df
    raise ValueError(source)


@dataclass
class ReferenceData:
    scored: pd.DataFrame
    features: Optional[pd.DataFrame]


class ReferenceCache:
    def __init__(self):
        self._d: Dict[Tuple[int, Tuple[str, ...]], ReferenceData] = {}

    def get(self, db: Session, model: InventoryModel, ref_periods: List[str]) -> ReferenceData:
        key = (model.id, tuple(ref_periods))
        if key not in self._d:
            prof = PROFILES[model_code(model)]
            scored = load_scored(db, model.id, ref_periods)
            feats = load_features(db, str(prof["features"]), model.id, ref_periods) if prof.get("features") else None
            self._d[key] = ReferenceData(scored, feats)
        return self._d[key]


# ---------------------------------------------------------------------------------------------
# Running monitoring
# ---------------------------------------------------------------------------------------------


def is_due(model: InventoryModel, period: str) -> bool:
    if model.monitoring_frequency == "Quarterly":
        return int(period[-2:]) in (3, 6, 9, 12)
    return True


def compute_metrics(model: InventoryModel, cur: pd.DataFrame, ref: ReferenceData,
                    cur_feats: Optional[pd.DataFrame]) -> Tuple[Dict[str, dict], List[dr.DriftResult]]:
    prof = PROFILES[model_code(model)]
    out: Dict[str, dict] = {}
    cls = mt.classification_metrics(cur["predicted"].astype(bool).values, cur["actual"].astype(bool).values)
    conf = cls.pop("_confusion")
    for k, v in cls.items():
        if k == "alert_false_positive_share":
            continue
        out[k] = {**v, "details": {"confusion": conf} if k in ("precision", "recall") else {}}
    out["false_positive_rate"]["details"] = {"alert_false_positive_share": cls["alert_false_positive_share"]["value"],
                                             "confusion": conf}
    if prof.get("conversion"):
        out["alert_conversion_rate"] = {**mt.alert_conversion_rate(cur["predicted"].values, cur["escalated"].values),
                                        "details": {}}
    if prof.get("override"):
        out["override_rate"] = {**mt.override_rate(cur["predicted"].values, cur["escalated"].values), "details": {}}
    ref_scores = ref.scored["score"].astype(float)
    if ref_scores.round(6).nunique() <= DISCRETE_SCORE_LEVELS:
        # Rules engines produce a few distinct scores (mostly zero); decile edges collapse, so bin by value
        psi_val, table = psi_categorical(ref_scores.round(6).map(_score_label), cur["score"].astype(float).round(6).map(_score_label))
        binning = "distinct score values"
    else:
        psi_val, table = psi_numeric(ref_scores.values, cur["score"].values)
        binning = "reference deciles"
    out["psi"] = {"value": psi_val, "numerator": None, "denominator": None,
                  "details": {"band": psi_band(psi_val), "bins": table, "binning": binning,
                              "reference_n": int(len(ref.scored)), "current_n": int(len(cur))}}
    dq = mt.dq_exception_rate(cur["dq_issue"].values)
    out["dq_exception_rate"] = {"value": dq["value"], "numerator": dq["numerator"], "denominator": dq["denominator"],
                                "details": {"by_rule": dq["by_rule"]}}
    drift_results: List[dr.DriftResult] = []
    if ref.features is not None and cur_feats is not None and len(cur_feats):
        for name, kind in FEATURES[str(prof["features"])]:
            fn = dr.numeric_drift if kind == "numeric" else dr.categorical_drift
            drift_results.append(fn(name, ref.features[name].values, cur_feats[name].values))
        if drift_results:
            worst = max(drift_results, key=lambda d: d.psi)
            out["max_feature_psi"] = {"value": worst.psi, "numerator": None, "denominator": None,
                                      "details": {"feature": worst.feature, "band": psi_band(worst.psi)}}
    return out, drift_results


def _previous_breach(db: Session, model_pk: int, metric: str, period: str) -> Optional[Breach]:
    prev_period = db.execute(select(func.max(MonitoringRun.period)).where(
        MonitoringRun.model_id == model_pk, MonitoringRun.period < period, MonitoringRun.is_latest.is_(True))).scalar()
    if prev_period is None:
        return None
    return db.execute(select(Breach).join(MonitoringRun, Breach.run_id == MonitoringRun.id).where(
        Breach.model_id == model_pk, Breach.metric == metric, Breach.period == prev_period,
        Breach.level == "Breach", MonitoringRun.is_latest.is_(True))).scalars().first()


def run_monitoring(db: Session, model: InventoryModel, period: str, triggered_by: Tuple[str, str],
                   cache: Optional[ReferenceCache] = None, write_audit: bool = True) -> MonitoringRun:
    code = model_code(model)
    if code not in PROFILES:
        raise WorkflowError(f"{model.model_id} has no scored-record monitoring profile")
    ref_periods = reference_periods(db)
    cache = cache or ReferenceCache()
    ref = cache.get(db, model, ref_periods)
    cur = load_scored(db, model.id, [period])
    if cur.empty:
        raise WorkflowError(f"No scored records for {model.model_id} in {period}")
    prof = PROFILES[code]
    cur_feats = load_features(db, str(prof["features"]), model.id, [period]) if prof.get("features") else None
    metric_values, drift_results = compute_metrics(model, cur, ref, cur_feats)

    # supersede earlier runs for the same model and period
    prior = list(db.execute(select(MonitoringRun).where(MonitoringRun.model_id == model.id,
                                                         MonitoringRun.period == period,
                                                         MonitoringRun.is_latest.is_(True))).scalars())
    for p in prior:
        p.is_latest = False
        db.execute(update(Breach).where(Breach.run_id == p.id, Breach.status != BreachStatus.RESOLVED.value)
                   .values(status=BreachStatus.RESOLVED.value, notes="Superseded by a re-run of monitoring"))
    seq = db.execute(select(func.count()).select_from(MonitoringRun).where(
        MonitoringRun.model_id == model.id, MonitoringRun.period == period)).scalar() + 1
    scenario = db.execute(select(SimulationPeriod.scenario).where(SimulationPeriod.period == period)).scalar() or "baseline"
    run = MonitoringRun(run_id=f"RUN-{period.replace('-', '')}-{model.model_id[4:]}-{seq:02d}", model_id=model.id,
                        period=period, reference_start=ref_periods[0], reference_end=ref_periods[-1],
                        record_count=int(len(cur)), reference_count=int(len(ref.scored)), scenario=scenario,
                        triggered_by=triggered_by[0], is_latest=True, overall_status="Within limits")
    db.add(run)
    db.flush()

    thresholds = {t.metric: t for t in model.thresholds if t.is_active}
    statuses = []
    new_breaches: List[Breach] = []
    for metric in METRIC_ORDER:
        if metric not in metric_values:
            continue
        mv = metric_values[metric]
        t = thresholds.get(metric)
        status = br.evaluate(mv["value"], t.direction, t.warning_limit, t.breach_limit) if t else "Not monitored"
        db.add(MetricResult(run_id=run.id, model_id=model.id, period=period, metric=metric, value=mv["value"],
                            numerator=mv.get("numerator"), denominator=mv.get("denominator"),
                            warning_limit=t.warning_limit if t else None, breach_limit=t.breach_limit if t else None,
                            direction=t.direction if t else None, status=status, details=mv.get("details") or {}))
        statuses.append(status)
        if t is None:
            continue
        # Only the latest period's result is the open item for a metric: earlier open records close here
        note = (f"Metric returned within limits in {period}" if status == "Within limits"
                else f"Superseded by the {period} result ({status})")
        if status in ("Within limits", "Warning", "Breach"):
            db.execute(update(Breach).where(Breach.model_id == model.id, Breach.metric == metric,
                                            Breach.period < period,
                                            Breach.status != BreachStatus.RESOLVED.value)
                       .values(status=BreachStatus.RESOLVED.value, notes=note))
        if status in ("Warning", "Breach"):
            consecutive = 1
            if status == "Breach":
                prev = _previous_breach(db, model.id, metric, period)
                consecutive = (prev.consecutive_periods + 1) if prev else 1
            sev, why = br.severity(mv["value"], t.direction, t.warning_limit, t.breach_limit, consecutive,
                                   model.risk_rating)
            b = Breach(breach_id=f"BR-{period.replace('-', '')}-{model.model_id[4:]}-{METRIC_ORDER.index(metric):02d}-{seq:02d}",
                       run_id=run.id, model_id=model.id, period=period, metric=metric, value=float(mv["value"]),
                       warning_limit=t.warning_limit, breach_limit=t.breach_limit, direction=t.direction,
                       level=status, severity=sev, consecutive_periods=consecutive, severity_rationale=why,
                       status=BreachStatus.OPEN.value)
            db.add(b)
            new_breaches.append(b)
    for d in drift_results:
        db.add(FeatureDrift(run_id=run.id, feature=d.feature, feature_type=d.feature_type, psi=d.psi,
                            test_name=d.test_name, statistic=d.statistic, p_value=d.p_value,
                            effect_size=d.effect_size, drift_flag=d.flag, drift_level=d.level,
                            details={"bins": d.table}))
    run.overall_status = "Breach" if "Breach" in statuses else ("Warning" if "Warning" in statuses else "Within limits")
    db.flush()
    if write_audit:
        summary = f"{model.model_id} {period}: {run.overall_status}"
        if new_breaches:
            summary += " (" + ", ".join(f"{b.metric} {b.severity}" for b in new_breaches) + ")"
        audit.record(db, triggered_by[0], triggered_by[1], "MONITORING_RUN", "model", model.model_id, summary,
                     {"run_id": run.run_id, "period": period, "records": run.record_count,
                      "breaches": [{"metric": b.metric, "value": round(b.value, 4), "level": b.level,
                                    "severity": b.severity} for b in new_breaches]})
    return run


def monitored_models(db: Session) -> List[InventoryModel]:
    return [m for m in db.execute(select(InventoryModel).where(InventoryModel.is_archived.is_(False))
                                  .order_by(InventoryModel.model_id)).unique().scalars()
            if model_code(m) in PROFILES and m.is_monitored]


def run_period(db: Session, period: str, triggered_by: Tuple[str, str], cache: Optional[ReferenceCache] = None,
               write_audit: bool = True, respect_frequency: bool = True) -> List[MonitoringRun]:
    cache = cache or ReferenceCache()
    runs = []
    for m in monitored_models(db):
        if respect_frequency and not is_due(m, period):
            continue
        runs.append(run_monitoring(db, m, period, triggered_by, cache, write_audit))
    return runs


# ---------------------------------------------------------------------------------------------
# Thresholds, frequency, breaches
# ---------------------------------------------------------------------------------------------

METRIC_DIRECTIONS = {"precision": "min", "recall": "min", "f1": "min", "false_positive_rate": "max",
                     "alert_rate": "max", "alert_conversion_rate": "min", "override_rate": "max", "psi": "max",
                     "max_feature_psi": "max", "dq_exception_rate": "max", "factual_accuracy": "min",
                     "hallucination_rate": "max", "unsupported_claim_rate": "max", "policy_compliance": "min",
                     "response_consistency": "min"}


def set_thresholds(db: Session, user, model: InventoryModel, items: List[dict]) -> List[ModelThreshold]:
    existing = {t.metric: t for t in model.thresholds}
    before = {k: {"warning": t.warning_limit, "breach": t.breach_limit, "active": t.is_active}
              for k, t in existing.items()}
    for it in items:
        metric = it["metric"]
        if metric not in METRIC_DIRECTIONS:
            raise WorkflowError(f"Unknown metric '{metric}'")
        direction = METRIC_DIRECTIONS[metric]
        try:
            br.validate_limits(direction, it["warning_limit"], it["breach_limit"])
        except ValueError as e:
            raise WorkflowError(f"{metric}: {e}") from e
        t = existing.get(metric)
        if t is None:
            t = ModelThreshold(model_id=model.id, metric=metric, direction=direction,
                               kind="KPI" if direction == "min" else "KRI", warning_limit=0, breach_limit=0)
            db.add(t)
            model.thresholds.append(t)
        t.warning_limit = float(it["warning_limit"])
        t.breach_limit = float(it["breach_limit"])
        t.is_active = bool(it.get("is_active", True))
        t.rationale = it["rationale"]
    db.flush()
    after = {t.metric: {"warning": t.warning_limit, "breach": t.breach_limit, "active": t.is_active}
             for t in model.thresholds}
    delta = audit.diff(before, after)
    if delta:
        audit.record(db, user.username, user.role, "THRESHOLDS_CHANGED", "model", model.model_id,
                     f"Changed monitoring thresholds: {', '.join(sorted(delta))}", delta)
    return list(model.thresholds)


def set_frequency(db: Session, user, model: InventoryModel, frequency: str) -> None:
    if frequency not in ("Monthly", "Quarterly"):
        raise WorkflowError("Frequency must be Monthly or Quarterly")
    if frequency == model.monitoring_frequency:
        return
    old = model.monitoring_frequency
    model.monitoring_frequency = frequency
    audit.record(db, user.username, user.role, "MONITORING_FREQUENCY_CHANGED", "model", model.model_id,
                 f"Monitoring frequency {old} to {frequency}", {"monitoring_frequency": {"from": old, "to": frequency}})


def acknowledge_breach(db: Session, user, breach_id: str, notes: str, resolve: bool = False) -> Breach:
    b = db.execute(select(Breach).where(Breach.breach_id == breach_id)).scalar_one_or_none()
    if b is None:
        raise NotFound(f"Breach {breach_id} not found")
    model = db.get(InventoryModel, b.model_id)
    if user.role == "model_owner" and user.id not in (model.business_owner_id, model.model_risk_owner_id):
        from app.core.errors import Forbidden

        raise Forbidden("Only the model's owners, validators or administrators can acknowledge this breach")
    if b.status == BreachStatus.RESOLVED.value:
        raise WorkflowError("Breach is already resolved")
    old = b.status
    if resolve:
        if user.role not in ("admin", "validator"):
            from app.core.errors import Forbidden

            raise Forbidden("Only validators or administrators can resolve a breach manually")
        b.status = BreachStatus.RESOLVED.value
    else:
        if b.status == BreachStatus.ACKNOWLEDGED.value:
            raise WorkflowError("Breach already acknowledged")
        b.status = BreachStatus.ACKNOWLEDGED.value
        b.acknowledged_by = user.username
        b.acknowledged_at = datetime.now(timezone.utc)
    b.notes = notes
    audit.record(db, user.username, user.role, "BREACH_RESOLVED" if resolve else "BREACH_ACKNOWLEDGED", "breach",
                 b.breach_id, f"{model.model_id} {b.metric} ({b.severity}): {notes[:120]}",
                 {"status": {"from": old, "to": b.status}, "notes": notes})
    return b


# ---------------------------------------------------------------------------------------------
# Queries for the API
# ---------------------------------------------------------------------------------------------


def latest_runs(db: Session) -> Dict[int, MonitoringRun]:
    sub = select(MonitoringRun.model_id, func.max(MonitoringRun.period).label("p")).where(
        MonitoringRun.is_latest.is_(True)).group_by(MonitoringRun.model_id).subquery()
    rows = db.execute(select(MonitoringRun).join(sub, and_(MonitoringRun.model_id == sub.c.model_id,
                                                           MonitoringRun.period == sub.c.p))
                      .where(MonitoringRun.is_latest.is_(True))).scalars()
    return {r.model_id: r for r in rows}


def open_breach_counts(db: Session) -> Dict[int, Dict[str, int]]:
    rows = db.execute(select(Breach.model_id, Breach.severity, func.count()).where(
        Breach.status != BreachStatus.RESOLVED.value).group_by(Breach.model_id, Breach.severity)).all()
    out: Dict[int, Dict[str, int]] = {}
    for mid, sev, n in rows:
        out.setdefault(mid, {})[sev] = n
    return out


def worst_severity(counts: Dict[str, int]) -> Optional[str]:
    if not counts:
        return None
    return max(counts, key=lambda s: SEVERITY_ORDER.get(s, 0))


def next_due(model: InventoryModel, last_period: Optional[str]) -> Optional[str]:
    from app.simulation.world import add_months

    if last_period is None:
        return None
    if model.monitoring_frequency == "Quarterly":
        p = add_months(last_period, 1)
        while int(p[-2:]) not in (3, 6, 9, 12):
            p = add_months(p, 1)
        return p
    return add_months(last_period, 1)


def today_or(d: Optional[date]) -> date:
    return d or date.today()
