"""In-app drift scenario: generate the next monthly period with a chosen drift level, score it with every
model, load it, and run monitoring so the resulting alerts and breaches can be observed."""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Dict

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import app.models as m
from app.core.errors import WorkflowError
from app.services import audit, monitoring
from app.simulation.pipeline import simulate_period
from app.simulation.world import SCENARIO_INTENSITY, WorldConfig, add_months, period_bounds

MAX_SIMULATED_PERIODS = 12


def config_from_db(db: Session) -> WorldConfig:
    w = monitoring.world_settings(db)
    return WorldConfig(seed=w["seed"], anchor=date.fromisoformat(w["anchor"]), history_months=w["history_months"],
                       reference_months=w["reference_months"], n_customers=w["n_customers"],
                       drift_scenario=w["drift_scenario"], drift_periods=w["drift_periods"])


def _lookback(db: Session, period: str) -> pd.DataFrame:
    _, end = period_bounds(period)
    cols = [m.Transaction.txn_id, m.Transaction.customer_id, m.Transaction.booking_date, m.Transaction.period,
            m.Transaction.amount_usd, m.Transaction.currency, m.Transaction.channel, m.Transaction.direction,
            m.Transaction.counterparty_name, m.Transaction.counterparty_country, m.Transaction.is_suspicious,
            m.Transaction.typology, m.Transaction.dq_issue]
    res = db.execute(select(*cols).where(m.Transaction.period == period,
                                         m.Transaction.booking_date >= end - timedelta(days=7)))
    return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


def simulate_next(db: Session, user, scenario: str) -> Dict[str, object]:
    if scenario not in SCENARIO_INTENSITY:
        raise WorkflowError("scenario must be none, moderate or severe")
    simulated = db.execute(select(func.count()).select_from(m.SimulationPeriod).where(
        m.SimulationPeriod.source == "simulation")).scalar()
    if simulated >= MAX_SIMULATED_PERIODS:
        raise WorkflowError(f"At most {MAX_SIMULATED_PERIODS} simulated periods; reset the simulation first")
    t0 = time.time()
    cfg = config_from_db(db)
    last = db.execute(select(func.max(m.SimulationPeriod.period))).scalar()
    period = add_months(last, 1)
    intensity = SCENARIO_INTENSITY[scenario]
    out = simulate_period(cfg, period, intensity, "baseline" if scenario == "none" else scenario, _lookback(db, last))

    from app.seed.run import load_period

    model_pk = {mm.model_id: mm.id for mm in db.execute(select(m.InventoryModel)).unique().scalars()}
    counts = load_period(db, out, model_pk)
    idx = db.execute(select(func.max(m.SimulationPeriod.period_index))).scalar() + 1
    db.add(m.SimulationPeriod(period=period, period_index=idx, scenario=out.scenario, drift_intensity=intensity,
                              is_reference=False, source="simulation",
                              notes=f"Simulated by {user.username} with scenario '{scenario}'"))
    # keep customer risk ratings current with the latest month
    latest = out.customer_scores.set_index("customer_id")
    for c in db.execute(select(m.Customer)).scalars():
        if c.customer_id in latest.index:
            c.risk_score = round(float(latest.at[c.customer_id, "score"]), 2)
            c.risk_rating = str(latest.at[c.customer_id, "rating"])
    db.flush()
    runs = monitoring.run_period(db, period, (user.username, user.role))
    breaches = [b for r in runs for b in db.execute(select(m.Breach).where(m.Breach.run_id == r.id)).scalars()]
    by_sev: Dict[str, int] = {}
    for b in breaches:
        if b.level == "Breach":
            by_sev[b.severity] = by_sev.get(b.severity, 0) + 1
    result = {"period": period, "scenario": scenario, "drift_intensity": intensity, "records": counts,
              "monitoring_runs": len(runs), "breaches": by_sev,
              "warnings": sum(1 for b in breaches if b.level == "Warning"),
              "models_in_breach": sorted({db.get(m.InventoryModel, r.model_id).model_id for r in runs
                                          if r.overall_status == "Breach"}),
              "seconds": round(time.time() - t0, 1)}
    audit.record(db, user.username, user.role, "SIMULATION_RUN", "dataset", period,
                 f"Simulated {period} with '{scenario}' drift: {sum(by_sev.values())} breaches", result)
    return result


def reset_simulation(db: Session, user) -> Dict[str, object]:
    periods = list(db.execute(select(m.SimulationPeriod.period).where(m.SimulationPeriod.source == "simulation"))
                   .scalars())
    if not periods:
        raise WorkflowError("There are no simulated periods to remove")
    run_ids = list(db.execute(select(m.MonitoringRun.id).where(m.MonitoringRun.period.in_(periods))).scalars())
    for model in (m.Breach, m.MetricResult, m.FeatureDrift):
        db.execute(delete(model).where(model.run_id.in_(run_ids)))
    db.execute(delete(m.MonitoringRun).where(m.MonitoringRun.id.in_(run_ids)))
    for model in (m.ScoredRecord, m.Alert, m.Transaction, m.Application, m.MediaArticle, m.SimulationPeriod):
        db.execute(delete(model).where(model.period.in_(periods)))
    audit.record(db, user.username, user.role, "SIMULATION_RESET", "dataset", ",".join(periods)[:48],
                 f"Removed {len(periods)} simulated period(s); audit history retained", {"periods": periods})
    return {"removed_periods": periods}
