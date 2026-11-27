"""Seeds governance records that depend on the synthetic history."""
from __future__ import annotations

from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.monitoring import MetricResult
from app.services import audit, monitoring
from app.simulation.world import WorldConfig

SYSTEM = ("system", "system")


def seed_monitoring(db: Session, cfg: WorldConfig, progress: Callable[[str], None]) -> None:
    cache = monitoring.ReferenceCache()
    total = 0
    for period in cfg.periods:
        runs = monitoring.run_period(db, period, SYSTEM, cache, write_audit=False)
        total += len(runs)
    db.flush()
    # Document each threshold with the range actually observed in the reference window
    for model in monitoring.monitored_models(db):
        for t in model.thresholds:
            vals = list(db.execute(select(MetricResult.value).where(
                MetricResult.model_id == model.id, MetricResult.metric == t.metric,
                MetricResult.period.in_(cfg.reference_periods), MetricResult.value.isnot(None))).scalars())
            if vals:
                t.rationale = (f"{t.rationale} Reference window {cfg.reference_periods[0]} to "
                               f"{cfg.reference_periods[-1]} observed {min(vals):.3f} to {max(vals):.3f}.")
    audit.record(db, *SYSTEM, "MONITORING_BACKFILL", "dataset", f"{cfg.periods[0]}..{cfg.periods[-1]}",
                 f"Ran {total} monitoring runs over {len(cfg.periods)} periods", {"runs": total})
    progress(f"monitoring backfilled: {total} runs")


def seed_all(db: Session, cfg: WorldConfig, settings: Settings, progress: Callable[[str], None]) -> None:
    from app.seed.validations import seed_validations

    seed_monitoring(db, cfg, progress)
    db.flush()
    seed_validations(db, cfg.anchor, progress)
    db.flush()
    from app.seed.ai import seed_ai
    from app.seed.regulatory import seed_regulatory
    from app.services import regulatory

    seed_ai(db, cfg.anchor, progress)
    db.flush()
    seed_regulatory(db, settings.today(), progress)
    db.flush()
    results = regulatory.run_tests(db, SYSTEM, settings.today())
    progress(f"control tests: {sum(r.result == 'Pass' for r in results)} pass, "
             f"{sum(r.result == 'Fail' for r in results)} with exceptions")
