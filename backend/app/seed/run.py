"""Build the database from scratch: schema migrations, reference data, synthetic history, governance records."""
from __future__ import annotations

import logging
import secrets
import time
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models as m
from app.core.config import BACKEND_DIR, Settings
from app.core.enums import DOCUMENTATION_ARTIFACTS
from app.core.security import hash_password
from app.db.base import Base
from app.seed import reference as ref
from app.services import audit
from app.services.inventory import derive_documentation_status
from app.simulation.pipeline import MODEL_IDS, PeriodOutput, generate_history
from app.simulation.world import WorldConfig, default_anchor

log = logging.getLogger("modelguard.seed")
SYSTEM = ("system", "system")


def world_config(settings: Settings) -> WorldConfig:
    return WorldConfig(
        seed=settings.seed,
        anchor=settings.anchor_date or default_anchor(settings.as_of_date),
        history_months=settings.history_months,
        drift_scenario=settings.drift_scenario,
        drift_periods=settings.drift_periods,
    )


def alembic_config(engine: Engine) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = str(engine.url.render_as_string(hide_password=False))
    return cfg


def reset_schema(engine: Engine) -> None:
    """Drop every table (the audit triggers do not block DROP) and re-run migrations."""
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        else:
            Base.metadata.drop_all(conn)
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    with engine.begin() as conn:
        cfg = alembic_config(engine)
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def upgrade_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        cfg = alembic_config(engine)
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def _bulk(db: Session, model, rows: List[dict], chunk: int = 20000) -> None:
    for i in range(0, len(rows), chunk):
        db.execute(insert(model), rows[i:i + chunk])


def _records(df: pd.DataFrame) -> List[dict]:
    out = df.astype(object).where(pd.notna(df), None).to_dict("records")
    return out


def seed_users(db: Session, password: str) -> Dict[str, m.User]:
    users = {}
    pw_hash = hash_password(password)
    for username, full_name, role, title, bu in ref.USERS:
        u = m.User(username=username, full_name=full_name, email=f"{username}@candela-bank.example",
                   title=title, role=role, business_unit=bu, password_hash=pw_hash)
        db.add(u)
        users[username] = u
    db.flush()
    audit.record(db, *SYSTEM, "SEED_USERS", "user", "all", f"Created {len(users)} synthetic staff accounts",
                 {"usernames": sorted(users)})
    return users


def seed_models(db: Session, users: Dict[str, m.User], anchor: date) -> Dict[str, m.InventoryModel]:
    def d(offset):
        return None if offset is None else anchor + timedelta(days=offset)

    out = {}
    for spec in ref.MODELS:
        checklist = spec["docs"]
        doc_review = d(spec["doc_review"])
        model = m.InventoryModel(
            model_id=spec["model_id"], name=spec["name"], description=spec["description"],
            business_owner_id=users[spec["business_owner"]].id, model_risk_owner_id=users[spec["model_risk_owner"]].id,
            developer=spec["developer"], business_unit=spec["business_unit"], category=spec["category"],
            methodology=spec["methodology"], methodology_type=spec["methodology_type"], vendor=spec["vendor"],
            version=spec["version"], geographies=spec["geographies"], risk_rating=spec["risk_rating"],
            risk_rationale=spec["risk_rationale"], lifecycle_stage=spec["lifecycle_stage"],
            supervisory_classification=spec["supervisory_classification"],
            classification_rationale=spec["classification_rationale"],
            implementation_date=d(spec["impl"]), last_validation_date=d(spec["last_val"]),
            next_validation_date=d(spec["next_val"]), approval_status=spec["approval_status"],
            documentation_checklist=checklist, documentation_reviewed_on=doc_review,
            documentation_status=derive_documentation_status(checklist, doc_review, anchor),
            limitations=spec["limitations"], monitoring_frequency=spec["monitoring_frequency"],
            is_monitored=True,
        )
        db.add(model)
        db.flush()
        for metric, (kind, direction, warn, breach, why) in ref.THRESHOLDS.get(spec["model_id"], {}).items():
            db.add(m.ModelThreshold(model_id=model.id, metric=metric, kind=kind, direction=direction,
                                    warning_limit=warn, breach_limit=breach, rationale=why))
        audit.record(db, *SYSTEM, "MODEL_CREATED", "model", model.model_id, f"Registered {model.name} in the inventory",
                     {"risk_rating": model.risk_rating, "lifecycle_stage": model.lifecycle_stage})
        out[spec["model_id"]] = model
    db.flush()
    return out


def load_period(db: Session, out: PeriodOutput, model_pk: Dict[str, int]) -> Dict[str, int]:
    t = out.transactions.copy()
    t = t[["txn_id", "customer_id", "booking_date", "period", "amount_usd", "currency", "channel", "direction",
           "counterparty_name", "counterparty_country", "is_suspicious", "typology", "dq_issue"]]
    t["scenario"] = out.scenario
    _bulk(db, m.Transaction, _records(t))

    a = out.applications.copy()
    a["scenario"] = out.scenario
    _bulk(db, m.Application, _records(a))

    ar = out.articles.copy()
    ar["scenario"] = out.scenario
    _bulk(db, m.MediaArticle, _records(ar.drop(columns=["dq_issue"])))

    if not out.alerts.empty:
        al = out.alerts.copy()
        al["model_id"] = al["model_code"].map(lambda c: model_pk[MODEL_IDS[c]])
        _bulk(db, m.Alert, _records(al.drop(columns=["model_code"])))

    sc = out.scored.copy()
    sc["model_id"] = sc["model_code"].map(lambda c: model_pk[MODEL_IDS[c]])
    _bulk(db, m.ScoredRecord, _records(sc.drop(columns=["model_code"])))
    return {"transactions": len(t), "applications": len(a), "articles": len(ar), "alerts": len(out.alerts),
            "scored_records": len(sc)}


def seed_synthetic(db: Session, cfg: WorldConfig, models: Dict[str, m.InventoryModel],
                   progress: Callable[[str], None]) -> dict:
    t0 = time.time()
    hist = generate_history(cfg)
    progress(f"generated {len(hist.outputs)} periods in {time.time() - t0:.1f}s")
    model_pk = {k: v.id for k, v in models.items()}

    latest = hist.outputs[-1].customer_scores.set_index("customer_id")
    cust = hist.world.customers.copy()
    cust["risk_score"] = cust["customer_id"].map(latest["score"]).round(2)
    cust["risk_rating"] = cust["customer_id"].map(latest["rating"])
    cust = cust.drop(columns=["cash_heavy_legit", "pass_through_legit", "hr_corridor_legit"])
    _bulk(db, m.Customer, _records(cust))
    wl = hist.world.watchlists.drop(columns=["region"])
    _bulk(db, m.WatchlistEntry, _records(wl))

    totals: Dict[str, int] = {}
    for i, out in enumerate(hist.outputs):
        counts = load_period(db, out, model_pk)
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
        db.add(m.SimulationPeriod(period=out.period, period_index=i, scenario=out.scenario,
                                  drift_intensity=out.intensity, is_reference=i < cfg.reference_months,
                                  source="seed"))
    db.merge(m.SystemSetting(key="world_config", value={
        "seed": cfg.seed, "anchor": cfg.anchor.isoformat(), "history_months": cfg.history_months,
        "reference_months": cfg.reference_months, "n_customers": cfg.n_customers,
        "drift_scenario": cfg.drift_scenario, "drift_periods": cfg.drift_periods,
        "periods": cfg.periods, "reference_periods": cfg.reference_periods,
    }))
    db.merge(m.SystemSetting(key="fitted_models", value=hist.suite.info))
    totals["customers"] = len(cust)
    totals["watchlist_entries"] = len(wl)
    audit.record(db, *SYSTEM, "SEED_SYNTHETIC_DATA", "dataset", f"seed-{cfg.seed}",
                 f"Generated {cfg.history_months} months of synthetic activity", totals)
    return totals


def seed_database(engine: Engine, settings: Settings, progress: Optional[Callable[[str], None]] = None,
                  password: Optional[str] = None) -> dict:
    progress = progress or (lambda s: log.info(s))
    pw = password or settings.demo_password
    generated = False
    if not pw:
        pw = secrets.token_urlsafe(12)
        generated = True
    reset_schema(engine)
    progress("schema migrated")
    cfg = world_config(settings)
    with Session(engine) as db:
        users = seed_users(db, pw)
        models = seed_models(db, users, cfg.anchor)
        totals = seed_synthetic(db, cfg, models, progress)
        db.commit()
        progress(f"synthetic data loaded: {totals}")
        # Later milestones extend the seed here
        from app.seed import governance

        governance.seed_all(db, cfg, settings, progress)
        db.commit()
    return {"totals": totals, "anchor": cfg.anchor.isoformat(), "periods": cfg.periods,
            "generated_password": pw if generated else None}


def table_counts(engine: Engine) -> Dict[str, int]:
    names = inspect(engine).get_table_names()
    with engine.connect() as conn:
        return {n: conn.execute(text(f'SELECT COUNT(*) FROM "{n}"')).scalar() for n in sorted(names)
                if n != "alembic_version"}


__all__ = ["seed_database", "reset_schema", "upgrade_schema", "world_config", "table_counts",
           "DOCUMENTATION_ARTIFACTS"]
