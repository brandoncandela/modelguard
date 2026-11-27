"""Milestone 3: monitoring runs are computed from the scored records, breaches follow thresholds,
and the drift simulation produces observable breaches."""
from __future__ import annotations

from sqlalchemy import func, select

import app.models as m


def test_backfill_covers_every_period(db):
    n = db.execute(select(func.count()).select_from(m.MonitoringRun).where(m.MonitoringRun.is_latest.is_(True))).scalar()
    assert n == 9 * 12  # nine scored-record models, twelve periods


def test_stored_precision_matches_raw_records(db):
    """Independent recomputation in SQL of one stored metric."""
    tm = db.execute(select(m.InventoryModel).where(m.InventoryModel.model_id == "MDL-TM-001")).unique().scalar_one()
    tp = db.execute(select(func.count()).select_from(m.ScoredRecord).where(
        m.ScoredRecord.model_id == tm.id, m.ScoredRecord.period == "2026-10", m.ScoredRecord.predicted.is_(True),
        m.ScoredRecord.actual.is_(True))).scalar()
    alerts = db.execute(select(func.count()).select_from(m.ScoredRecord).where(
        m.ScoredRecord.model_id == tm.id, m.ScoredRecord.period == "2026-10",
        m.ScoredRecord.predicted.is_(True))).scalar()
    stored = db.execute(select(m.MetricResult.value).join(m.MonitoringRun).where(
        m.MetricResult.model_id == tm.id, m.MetricResult.period == "2026-10", m.MetricResult.metric == "precision",
        m.MonitoringRun.is_latest.is_(True))).scalar()
    assert stored == tp / alerts


def test_reference_window_is_stable_and_drift_window_breaches(db):
    rows = db.execute(select(m.Breach.period, m.InventoryModel.model_id).join(m.InventoryModel).where(
        m.Breach.level == "Breach", m.InventoryModel.model_id.in_(["MDL-TM-001", "MDL-SAD-007", "MDL-AM-006"]))).all()
    periods = {p for p, _ in rows}
    assert periods and min(periods) >= "2026-08"  # breaches only appear once drift starts
    psis = db.execute(select(m.MetricResult.value).join(m.InventoryModel).where(
        m.InventoryModel.model_id == "MDL-TM-001", m.MetricResult.metric == "psi",
        m.MetricResult.period <= "2026-04")).scalars().all()
    assert max(psis) < 0.10


def test_summary_and_series(client, auth):
    s = client.get("/api/v1/monitoring/summary", headers=auth("nbrooks")).json()
    by_id = {r["model_id"]: r for r in s["models"]}
    assert by_id["MDL-LLM-009"]["monitored_via"] == "llm_evaluation"
    assert by_id["MDL-TM-001"]["latest_period"] == "2026-10"
    assert by_id["MDL-TM-001"]["metrics"]["recall"]["value"] is not None
    assert len(s["periods"]) == 12 and s["reference_periods"][0] == "2025-11"
    ser = client.get("/api/v1/monitoring/models/MDL-SAD-007/series", params={"metrics": "recall,psi"},
                     headers=auth("nbrooks")).json()
    assert len(ser["series"]["recall"]) == 12
    dist = client.get("/api/v1/monitoring/models/MDL-SAD-007/distribution", headers=auth("nbrooks")).json()
    assert len(dist["bins"]) == 10 and abs(sum(b["actual_share"] for b in dist["bins"]) - 1) < 1e-9
    meth = client.get("/api/v1/monitoring/methodology", headers=auth("jpatel")).json()
    assert {d["metric"] for d in meth["metrics"]} >= {"precision", "recall", "psi", "dq_exception_rate"}
    assert meth["model_parameters"]["MDL-SAD-007"]["algorithm"] == "HistGradientBoostingClassifier"


def test_run_detail_has_drift_tests(client, auth):
    runs = client.get("/api/v1/monitoring/models/MDL-TM-001/runs", headers=auth("nbrooks")).json()
    detail = client.get(f"/api/v1/monitoring/runs/{runs[0]['run_id']}", headers=auth("nbrooks")).json()
    tests = {d["feature"]: d["test"] for d in detail["drift"]}
    assert tests["amount_usd"] == "Kolmogorov-Smirnov" and tests["channel"] == "Chi-square"


def test_threshold_validation_and_permissions(client, auth):
    bad = {"items": [{"metric": "recall", "warning_limit": 0.40, "breach_limit": 0.50,
                      "rationale": "Testing an inverted limit pair"}]}
    assert client.put("/api/v1/monitoring/models/MDL-TM-001/thresholds", json=bad,
                      headers=auth("jpatel")).status_code == 422
    good = {"items": [{"metric": "recall", "warning_limit": 0.60, "breach_limit": 0.55,
                       "rationale": "Tightened after examiner feedback on scenario coverage"}]}
    assert client.put("/api/v1/monitoring/models/MDL-TM-001/thresholds", json=good,
                      headers=auth("nbrooks")).status_code == 403  # validators cannot configure
    assert client.put("/api/v1/monitoring/models/MDL-TM-001/thresholds", json=good,
                      headers=auth("skim")).status_code == 403  # not this owner's model
    r = client.put("/api/v1/monitoring/models/MDL-TM-001/thresholds", json=good, headers=auth("jpatel"))
    assert r.status_code == 200
    rec = next(t for t in r.json() if t["metric"] == "recall")
    assert rec["warning_limit"] == 0.60

    # re-running the latest period applies the new limits and supersedes the old run
    r = client.post("/api/v1/monitoring/runs", json={"model_id": "MDL-TM-001", "period": "2026-10"},
                    headers=auth("jpatel"))
    assert r.status_code == 200 and r.json()[0]["overall_status"] == "Breach"
    runs = client.get("/api/v1/monitoring/models/MDL-TM-001/runs", headers=auth("jpatel")).json()
    oct_runs = [x for x in runs if x["period"] == "2026-10"]
    assert len(oct_runs) == 2 and sum(x["is_latest"] for x in oct_runs) == 1
    hist = client.get("/api/v1/models/MDL-TM-001/history", headers=auth("jpatel")).json()
    assert hist[0]["action"] == "MONITORING_RUN" and hist[1]["action"] == "THRESHOLDS_CHANGED"


def test_acknowledge_breach(client, auth):
    items = client.get("/api/v1/monitoring/breaches", params={"status": "Open", "level": "Breach"},
                       headers=auth("skim")).json()["items"]
    sf = next(b for b in items if b["model_id"] == "MDL-SF-002")
    assert sf["severity"] in ("Medium", "High", "Critical")
    other = next(b for b in items if b["model_id"] == "MDL-TM-001")
    assert client.post(f"/api/v1/monitoring/breaches/{other['breach_id']}/acknowledge", json={"notes": "Looking"},
                       headers=auth("skim")).status_code == 403
    r = client.post(f"/api/v1/monitoring/breaches/{sf['breach_id']}/acknowledge",
                    json={"notes": "Payment platform migration ticket raised"}, headers=auth("skim"))
    assert r.status_code == 200 and r.json()["status"] == "Acknowledged"


def test_drift_simulation_generates_breaches(client, auth):
    assert client.post("/api/v1/monitoring/simulate", json={"scenario": "severe"},
                       headers=auth("jpatel")).status_code == 403
    r = client.post("/api/v1/monitoring/simulate", json={"scenario": "severe"}, headers=auth("admin"))
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["period"] == "2026-11" and res["drift_intensity"] == 1.0
    assert res["records"]["transactions"] > 4000
    assert sum(res["breaches"].values()) >= 5
    assert {"MDL-TM-001", "MDL-SAD-007", "MDL-AM-006"} <= set(res["models_in_breach"])
    s = client.get("/api/v1/monitoring/summary", headers=auth("admin")).json()
    tm = next(x for x in s["models"] if x["model_id"] == "MDL-TM-001")
    assert tm["latest_period"] == "2026-11" and tm["scenario"] == "severe"
    r = client.delete("/api/v1/monitoring/simulate", headers=auth("admin"))
    assert r.json()["removed_periods"] == ["2026-11"]
    s = client.get("/api/v1/monitoring/summary", headers=auth("admin")).json()
    assert next(x for x in s["models"] if x["model_id"] == "MDL-TM-001")["latest_period"] == "2026-10"
