"""Milestone 6: executive KPIs come from the data, committee packs and PDFs contain every required section."""
from __future__ import annotations

import hashlib
import io
from datetime import date

from pypdf import PdfReader
from sqlalchemy import func, select

import app.models as m

REQUIRED = ["Executive summary", "Key risk indicators", "Model inventory changes", "Validation outcomes",
            "Critical and High findings", "Remediation progress", "AI governance status", "Management recommendations"]


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_kpis_match_independent_queries(client, auth, db):
    k = client.get("/api/v1/dashboard/executive", headers=auth("hmarsh")).json()["kpis"]
    today = date(2026, 11, 25)
    active = db.execute(select(m.InventoryModel).where(m.InventoryModel.is_archived.is_(False))).unique().scalars().all()
    assert k["total_models"] == len(active) == 10
    assert k["high_risk_models"] == sum(1 for x in active if x.risk_rating == "High")
    assert k["overdue_validations"] == sum(1 for x in active if x.next_validation_date and x.next_validation_date < today)
    open_crit = db.execute(select(func.count()).select_from(m.Finding).where(
        m.Finding.severity == "Critical", m.Finding.status.notin_(["Closed", "Risk Accepted"]))).scalar()
    assert k["open_critical_findings"] == open_crit
    awaiting = db.execute(select(func.count()).select_from(m.AISystem).where(
        m.AISystem.approval_status.in_(["Draft", "Under Review"]))).scalar()
    assert k["ai_systems_awaiting_approval"] == awaiting
    assert 0 < k["documentation_completeness_pct"] < 100


def test_kpis_respond_to_changes(client, auth):
    before = client.get("/api/v1/dashboard/executive", headers=auth("admin")).json()["kpis"]
    client.post("/api/v1/models/MDL-PEP-005/archive", json={"reason": "Temporarily archived for KPI test"},
                headers=auth("admin"))
    after = client.get("/api/v1/dashboard/executive", headers=auth("admin")).json()["kpis"]
    assert after["total_models"] == before["total_models"] - 1
    client.post("/api/v1/models/MDL-PEP-005/restore", headers=auth("admin"))


def test_trends_are_reconstructed_from_history(client, auth):
    t = client.get("/api/v1/dashboard/trends", headers=auth("hmarsh")).json()
    ps = t["periods"]
    assert len(ps) == 12
    assert all(p["breaches"] == 0 for p in ps if p["is_reference"])
    assert ps[-1]["breaches"] > 0 and ps[-1]["models_in_breach"] > 0
    assert all(p["alerts"] > 300 for p in ps)
    assert t["validation_outcomes_by_quarter"]


def test_committee_packs(client, auth):
    mrmc = client.get("/api/v1/committees/mrmc", headers=auth("hmarsh")).json()
    assert mrmc["title"] == "Model Risk Management Committee" and len(mrmc["inventory"]) == 10
    assert mrmc["recommendations"] and "inventory holds 10" in mrmc["summary"]
    fc = client.get("/api/v1/committees/fcmoc", headers=auth("dosei")).json()
    assert len(fc["monitoring"]) == 8 and {c["control_id"] for c in fc["part504_controls"]} >= {"CTL-11", "CTL-12"}
    ai = client.get("/api/v1/committees/aigc", headers=auth("lferreira")).json()
    assert any(s["classification"].startswith("Pending review: High-risk") for s in ai["systems"])
    assert any("2 December 2027" in r for r in ai["recommendations"])
    assert client.get("/api/v1/committees/xyz", headers=auth("hmarsh")).status_code == 422


def test_generate_and_download_every_report(client, auth):
    for kind in ("executive", "mrmc", "fcmoc", "aigc"):
        r = client.post("/api/v1/reports", json={"report_type": kind}, headers=auth("hmarsh"))
        assert r.status_code == 201, r.text
        meta = r.json()
        dl = client.get(f"/api/v1/reports/{meta['report_id']}/download", headers=auth("jpatel"))
        assert dl.status_code == 200 and dl.headers["content-type"] == "application/pdf"
        assert dl.content[:5] == b"%PDF-"
        assert hashlib.sha256(dl.content).hexdigest() == meta["sha256"] == dl.headers["x-content-sha256"]
        text = _text(dl.content)
        assert "Synthetic data" in text and "Not a certification" in text
        if kind == "executive":
            for heading in REQUIRED:
                assert heading in text, heading
    hist = client.get("/api/v1/reports", headers=auth("hmarsh")).json()
    assert len(hist) >= 4
    ev = client.get("/api/v1/audit/events", params={"action": "REPORT_GENERATED"}, headers=auth("hmarsh")).json()
    assert ev["total"] >= 4


def test_validation_report(client, auth):
    vid = next(v["validation_id"] for v in client.get("/api/v1/validations", headers=auth("hmarsh")).json()
               if v["status"] == "Conditionally Approved" and v["model"]["model_id"] == "MDL-CRS-004")
    r = client.post(f"/api/v1/validations/{vid}/report", headers=auth("nbrooks"))
    assert r.status_code == 201
    pdf = client.get(f"/api/v1/reports/{r.json()['report_id']}/download", headers=auth("nbrooks")).content
    text = _text(pdf)
    for heading in ("Conclusion", "Scope and team", "Findings", "Evidence", "Approval record", "Workflow history"):
        assert heading in text
    assert vid in text
