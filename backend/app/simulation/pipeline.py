"""Period pipeline: generate raw activity, run data quality rules, score with every model,
create alerts and dispositions. Used both by the seed command and by the in-app drift simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.simulation import activity, detectors as det, dq
from app.simulation.world import (
    World,
    WorldConfig,
    add_months,
    build_world,
    period_bounds,
    rng_for,
)

MODEL_IDS = {
    "TM": "MDL-TM-001",
    "SF": "MDL-SF-002",
    "NS": "MDL-NS-003",
    "CRS": "MDL-CRS-004",
    "PEP": "MDL-PEP-005",
    "AM": "MDL-AM-006",
    "SAD": "MDL-SAD-007",
    "AII": "MDL-AII-008",
    "LLM": "MDL-LLM-009",
    "COR": "MDL-COR-010",
}
ALERTING = ["TM", "SAD", "SF", "NS", "PEP", "AM"]


def list_names(world: World) -> Dict[str, object]:
    wl = world.watchlists
    return {
        "SANCTIONS": wl.loc[wl.list_type == "SANCTIONS", "name"].tolist(),
        "PEP": wl.loc[wl.list_type == "PEP", "name"].tolist(),
        "SANCTIONS_WL": wl.loc[wl.list_type.isin(["SANCTIONS", "WATCHLIST"]), "name"].tolist(),
        "_region": dict(zip(wl["name"], wl["region"])),
    }


@dataclass
class Screeners:
    sanctions: det.Screener
    sanctions_wl: det.Screener
    pep: det.Screener

    @classmethod
    def build(cls, lists: Dict[str, object]) -> "Screeners":
        return cls(det.Screener(lists["SANCTIONS"]), det.Screener(lists["SANCTIONS_WL"]), det.Screener(lists["PEP"]))


@dataclass
class RawPeriod:
    period: str
    intensity: float
    transactions: pd.DataFrame
    applications: pd.DataFrame
    screen_names: pd.DataFrame
    articles: pd.DataFrame


@dataclass
class PeriodOutput:
    period: str
    intensity: float
    scenario: str
    transactions: pd.DataFrame
    applications: pd.DataFrame
    articles: pd.DataFrame
    scored: pd.DataFrame
    alerts: pd.DataFrame
    customer_scores: pd.DataFrame


@dataclass
class History:
    world: World
    lists: Dict[str, object]
    suite: det.ModelSuite
    outputs: List[PeriodOutput] = field(default_factory=list)


def generate_raw(world: World, lists, period: str, intensity: float) -> RawPeriod:
    txns = activity.generate_transactions(world, period, intensity, lists)
    txns["dq_issue"] = dq.check_transactions(txns, period).values
    apps, screen = activity.generate_applications(world, period, intensity, lists)
    apps["dq_issue"] = dq.check_applications(apps).values
    subjects = screen["name"].tolist()
    arts = activity.generate_articles(world, period, intensity, subjects)
    arts["dq_issue"] = dq.check_articles(arts).values
    return RawPeriod(period, intensity, txns, apps, screen, arts)


def screen_applications(scr: Screeners, screen: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    ns_score, ns_idx = scr.sanctions_wl.score(screen["name"].tolist())
    pep_score, pep_idx = scr.pep.score(screen["name"].tolist())
    s = screen.copy()
    s["ns_score"] = ns_score
    s["ns_match"] = [scr.sanctions_wl.names[i] for i in ns_idx] if len(ns_idx) else []
    s["pep_score"] = pep_score
    s["pep_match"] = [scr.pep.names[i] for i in pep_idx] if len(pep_idx) else []
    hit = (s["ns_score"] >= det.NS_THRESHOLD) | (s["pep_score"] >= det.PEP_THRESHOLD)
    app_hits = hit.groupby(s["application_id"]).max().astype(int)
    return s, app_hits


def fit_suite(world: World, lists, scr: Screeners, raws: List[RawPeriod]) -> det.ModelSuite:
    txns = pd.concat([r.transactions for r in raws], ignore_index=True)
    feats = det.transaction_features(txns, world.customers)
    apps = pd.concat([r.applications for r in raws], ignore_index=True)
    screen = pd.concat([r.screen_names for r in raws], ignore_index=True)
    _, hits = screen_applications(scr, screen)
    arts = pd.concat([r.articles for r in raws], ignore_index=True)
    return det.ModelSuite().fit(feats, apps, hits, arts, world.config.seed)


def _priority(score: np.ndarray, threshold: float, top: float) -> np.ndarray:
    r = (score - threshold) / max(top - threshold, 1e-9)
    return np.where(r >= 0.5, "High", np.where(r >= 0.2, "Medium", "Low"))


def _dispositions(rng: np.random.Generator, productive: np.ndarray, kind: str):
    """Simulate investigator outcomes. Investigators escalate most productive alerts and a few others."""
    n = len(productive)
    u = rng.random((n, 2))
    escalated = np.where(productive, u[:, 0] < 0.92, u[:, 0] < 0.07)
    sar = escalated & np.where(productive, u[:, 1] < 0.85, u[:, 1] < 0.10)
    if kind == "sanctions":
        disp = np.where(escalated & productive, "True match - payment rejected",
                        np.where(escalated, "Escalated - cleared on review", "False positive - released"))
        sar = np.zeros(n, dtype=bool)
    elif kind == "screening":
        disp = np.where(escalated, "Escalated to EDD", "False positive - cleared")
        sar = np.zeros(n, dtype=bool)
    else:
        disp = np.where(sar, "SAR filed", np.where(escalated, "Case closed - no SAR", "Closed - false positive"))
    return escalated, sar, disp


def score_period(world: World, lists, scr: Screeners, suite: det.ModelSuite, raw: RawPeriod, scenario: str,
                 lookback: Optional[pd.DataFrame] = None) -> PeriodOutput:
    period = raw.period
    cfg = world.config
    start, end = period_bounds(period)
    txns = raw.transactions
    allx = txns if lookback is None or lookback.empty else pd.concat([lookback, txns], ignore_index=True)
    feats_all = det.transaction_features(allx, world.customers)
    feats = feats_all[feats_all["period"] == period].copy()
    feats = feats.set_index("txn_id").loc[txns["txn_id"]].reset_index()
    seg_of = world.customers.set_index("customer_id")["segment"]

    scored: List[pd.DataFrame] = []
    alerts: List[pd.DataFrame] = []

    def add_scored(code, ref, score, predicted, actual, segment, dq_issue, escalated=None):
        scored.append(pd.DataFrame({
            "model_code": code, "period": period, "record_ref": list(ref), "score": np.round(np.asarray(score, float), 6),
            "predicted": np.asarray(predicted, bool), "actual": np.asarray(actual, bool),
            "escalated": [None] * len(ref) if escalated is None else list(escalated),
            "segment": list(segment), "dq_issue": [dq.none_if_nan(x) for x in dq_issue], "scenario": scenario,
        }))

    def add_alerts(code, frame, kind, threshold, top):
        """frame columns: record_ref, customer_id, score, actual, rule_hits, created_on"""
        if frame.empty:
            return np.zeros(0, bool)
        rng = rng_for(cfg.seed, "dispositions", period, code)
        esc, sar, disp = _dispositions(rng, frame["actual"].values.astype(bool), kind)
        a = pd.DataFrame({
            "model_code": code,
            "alert_id": [f"ALT-{period.replace('-', '')}-{code}-{i + 1:05d}" for i in range(len(frame))],
            "period": period, "created_on": list(frame["created_on"]), "subject_ref": list(frame["record_ref"]),
            "customer_id": list(frame["customer_id"]), "score": np.round(frame["score"].values.astype(float), 6),
            "rule_hits": list(frame["rule_hits"]), "priority": _priority(frame["score"].values.astype(float), threshold, top),
            "disposition": disp, "escalated": esc, "sar_filed": sar, "is_productive": frame["actual"].values.astype(bool),
        })
        alerts.append(a)
        return esc

    # --- MDL-TM-001 rules -----------------------------------------------------------------------
    tm, tm_hits = det.tm_score(feats)
    tm_pred = tm >= det.TM_ALERT_THRESHOLD
    tm_frame = pd.DataFrame({"record_ref": feats["txn_id"], "customer_id": feats["customer_id"], "score": tm,
                             "actual": feats["is_suspicious"], "rule_hits": tm_hits,
                             "created_on": [d + timedelta(days=1) for d in feats["booking_date"]]})[tm_pred]
    tm_esc = add_alerts("TM", tm_frame, "aml", det.TM_ALERT_THRESHOLD, 100.0)
    esc_full = np.full(len(feats), None, dtype=object)
    esc_full[np.where(tm_pred)[0]] = tm_esc
    add_scored("TM", feats["txn_id"], tm, tm_pred, feats["is_suspicious"], feats["segment"], feats["dq_issue"], esc_full)

    # --- MDL-SAD-007 gradient boosting ------------------------------------------------------------
    sad = suite.sad_scores(feats)
    sad_pred = sad >= suite.sad_threshold
    sad_frame = pd.DataFrame({"record_ref": feats["txn_id"], "customer_id": feats["customer_id"], "score": sad,
                              "actual": feats["is_suspicious"], "rule_hits": "model score",
                              "created_on": [d + timedelta(days=1) for d in feats["booking_date"]]})[sad_pred]
    sad_esc = add_alerts("SAD", sad_frame, "aml", suite.sad_threshold, 1.0)
    esc_full = np.full(len(feats), None, dtype=object)
    esc_full[np.where(sad_pred)[0]] = sad_esc
    add_scored("SAD", feats["txn_id"], sad, sad_pred, feats["is_suspicious"], feats["segment"], feats["dq_issue"],
               esc_full)

    # --- MDL-SF-002 sanctions filtering on cross-border payments -------------------------------
    home = txns["customer_id"].map(world.customers.set_index("customer_id")["country"])
    cross_mask = (txns["channel"].isin(["International wire", "Instant payment"])
                  & ((txns["counterparty_country"] != home) | txns["counterparty_country"].isna()))
    sf = txns[cross_mask]
    sf_score, sf_idx = scr.sanctions.score(sf["counterparty_name"].tolist())
    sf_pred = sf_score >= det.SF_THRESHOLD
    sf_frame = pd.DataFrame({"record_ref": sf["txn_id"].values, "customer_id": sf["customer_id"].values, "score": sf_score,
                             "actual": sf["cp_list_match"].values,
                             "rule_hits": [f"list match: {scr.sanctions.names[i]}" for i in sf_idx],
                             "created_on": list(sf["booking_date"].values)})[sf_pred]
    sf_esc = add_alerts("SF", sf_frame, "sanctions", det.SF_THRESHOLD, 1.0)
    esc_full = np.full(len(sf), None, dtype=object)
    esc_full[np.where(sf_pred)[0]] = sf_esc
    add_scored("SF", sf["txn_id"], sf_score, sf_pred, sf["cp_list_match"], sf["channel"], sf["dq_issue"], esc_full)

    # --- MDL-NS-003 and MDL-PEP-005 onboarding screening -----------------------------------------
    apps = raw.applications
    screen, app_hits = screen_applications(scr, raw.screen_names)
    app_dq = screen["application_id"].map(apps.set_index("application_id")["dq_issue"])
    app_day = {a: start + timedelta(days=int(i % (end - start).days)) for i, a in enumerate(apps["application_id"])}
    for code, col, truth, thr, match_col in (("NS", "ns_score", "sanctions_truth", det.NS_THRESHOLD, "ns_match"),
                                             ("PEP", "pep_score", "pep_truth", det.PEP_THRESHOLD, "pep_match")):
        pred = screen[col].values >= thr
        fr = pd.DataFrame({"record_ref": screen["screen_ref"].values, "customer_id": None, "score": screen[col].values,
                           "actual": screen[truth].values, "rule_hits": [f"list match: {m}" for m in screen[match_col]],
                           "created_on": [app_day[a] for a in screen["application_id"]]})[pred]
        esc = add_alerts(code, fr, "screening", thr, 1.0)
        esc_full = np.full(len(screen), None, dtype=object)
        esc_full[np.where(pred)[0]] = esc
        add_scored(code, screen["screen_ref"], screen[col], pred, screen[truth], screen["role"], app_dq, esc_full)

    # --- MDL-AM-006 adverse media classifier ----------------------------------------------------
    arts = raw.articles
    am = suite.am_scores(arts)
    am_pred = am >= det.AM_THRESHOLD
    am_frame = pd.DataFrame({"record_ref": arts["article_id"].values, "customer_id": None, "score": am,
                             "actual": arts["is_relevant"].values, "rule_hits": "relevance classifier",
                             "created_on": [start + timedelta(days=int(i % 28)) for i in range(len(arts))]})[am_pred]
    am_esc = add_alerts("AM", am_frame, "screening", det.AM_THRESHOLD, 1.0)
    esc_full = np.full(len(arts), None, dtype=object)
    esc_full[np.where(am_pred)[0]] = am_esc
    add_scored("AM", arts["article_id"], am, am_pred, arts["is_relevant"], ["Article"] * len(arts), arts["dq_issue"],
               esc_full)

    # --- MDL-CRS-004 customer risk scoring -----------------------------------------------------
    crs = det.crs_scores(world.customers, feats)
    truth = crs["customer_id"].map(world.customers.set_index("customer_id")["is_suspicious"])
    add_scored("CRS", crs["customer_id"], crs["score"], crs["rating"] == "High", truth,
               crs["customer_id"].map(seg_of), crs["dq_issue"])

    # --- MDL-COR-010 onboarding classification -------------------------------------------------
    cor = suite.cor_scores(apps, app_hits)
    add_scored("COR", apps["application_id"], cor, cor >= det.COR_THRESHOLD, apps["is_high_risk"], apps["segment"],
               apps["dq_issue"])

    # --- MDL-AII-008 AI triage recommendations on TM and SAD alerts (simulated outputs) ---------
    alert_df = pd.concat(alerts, ignore_index=True) if alerts else pd.DataFrame()
    s = raw.intensity
    if not alert_df.empty:
        tri = alert_df[alert_df["model_code"].isin(["TM", "SAD"])].reset_index(drop=True)
        rng = rng_for(cfg.seed, "ai-triage", period)
        prod = tri["is_productive"].values.astype(bool)
        p_esc = np.where(prod, 0.90 - 0.22 * s, 0.10 + 0.10 * s)
        rec = rng.random(len(tri)) < p_esc
        conf = np.where(rec, 0.5 + 0.5 * rng.beta(5, 2, len(tri)), 0.5 * rng.beta(2, 5, len(tri)))
        txn_dq = tri["subject_ref"].map(txns.set_index("txn_id")["dq_issue"])
        add_scored("AII", tri["alert_id"], conf, rec, prod, tri["model_code"], txn_dq, tri["escalated"].values)

    scored_df = pd.concat(scored, ignore_index=True)
    txns_out = txns.drop(columns=["cp_list_match"])
    return PeriodOutput(period, raw.intensity, scenario, txns_out, apps, arts, scored_df, alert_df, crs)


def scenario_label(cfg: WorldConfig, intensity: float) -> str:
    return "baseline" if intensity == 0 else cfg.drift_scenario


def generate_history(cfg: WorldConfig) -> History:
    world = build_world(cfg)
    lists = list_names(world)
    scr = Screeners.build(lists)
    raws = [generate_raw(world, lists, p, cfg.intensity(i)) for i, p in enumerate(cfg.periods)]
    suite = fit_suite(world, lists, scr, raws[: cfg.reference_months])
    hist = History(world=world, lists=lists, suite=suite)
    prev_tail = None
    for raw in raws:
        out = score_period(world, lists, scr, suite, raw, scenario_label(cfg, raw.intensity), prev_tail)
        hist.outputs.append(out)
        prev_tail = raw.transactions[pd.to_datetime(raw.transactions["booking_date"]) >= pd.Timestamp(
            period_bounds(raw.period)[1] - timedelta(days=7))].copy()
    return hist


_SUITE_CACHE: Dict[Tuple, Tuple[World, Dict, Screeners, det.ModelSuite]] = {}


def prepared(cfg: WorldConfig):
    """World, lists, screeners and fitted models for a config (cached per process)."""
    key = (cfg.seed, cfg.anchor, cfg.history_months, cfg.reference_months, cfg.n_customers)
    if key not in _SUITE_CACHE:
        world = build_world(cfg)
        lists = list_names(world)
        scr = Screeners.build(lists)
        raws = [generate_raw(world, lists, p, cfg.intensity(i)) for i, p in enumerate(cfg.reference_periods)]
        suite = fit_suite(world, lists, scr, raws)
        _SUITE_CACHE[key] = (world, lists, scr, suite)
    return _SUITE_CACHE[key]


def simulate_period(cfg: WorldConfig, period: str, intensity: float, scenario: str,
                    lookback: Optional[pd.DataFrame]) -> PeriodOutput:
    world, lists, scr, suite = prepared(cfg)
    raw = generate_raw(world, lists, period, intensity)
    lb = None
    if lookback is not None and not lookback.empty:
        lb = lookback.copy()
        if "cp_list_match" not in lb.columns:
            lb["cp_list_match"] = False
    return score_period(world, lists, scr, suite, raw, scenario, lb)


def next_period(last_period: str) -> str:
    return add_months(last_period, 1)
