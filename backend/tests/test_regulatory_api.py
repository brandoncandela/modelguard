"""Milestone 5: regulatory library, control mapping, automated control tests."""
from __future__ import annotations


def test_sources_mark_superseded_guidance(client, auth):
    body = client.get("/api/v1/regulatory/sources", headers=auth("jpatel")).json()
    src = {s["source_id"]: s for s in body["items"]}
    assert src["SR-11-7"]["status"] == "Superseded" and "SR 26-2" in src["SR-11-7"]["superseded_by"]
    assert src["OCC-2011-12"]["status"] == "Rescinded"
    assert src["SR-26-2"]["status"] == "Current"
    assert src["NYCRR-504"]["source_type"] == "Regulation"
    assert src["SR-26-2"]["source_type"] == "Supervisory guidance"
    assert src["MRM-POL-001"]["source_type"] == "Internal policy"
    assert all(s["url"].startswith("https://") for s in body["items"] if s["source_type"] != "Internal policy")
    assert "do not establish or guarantee compliance" in body["disclaimer"]


def test_requirements_and_coverage(client, auth):
    rows = client.get("/api/v1/regulatory/requirements", headers=auth("dosei")).json()["items"]
    by_id = {r["requirement_id"]: r for r in rows}
    assert by_id["SR117-REV"]["coverage"] == "Historical reference"
    assert by_id["504-TM"]["controls"] and by_id["504-TM"]["coverage"] in ("Covered", "Partially covered")
    assert {r["obligation_type"] for r in rows} == {"Supervisory guidance", "Regulation", "Internal policy"}
    cov = client.get("/api/v1/regulatory/coverage", headers=auth("dosei")).json()
    assert cov["controls"]["total"] == 21 and cov["controls"]["automated"] == 15


def test_control_tests_find_real_exceptions(client, auth):
    assert client.post("/api/v1/regulatory/controls/test", json={}, headers=auth("jpatel")).status_code == 403
    res = {r["control_id"]: r for r in client.post("/api/v1/regulatory/controls/test", json={},
                                                    headers=auth("hmarsh")).json()}
    assert res["CTL-19"]["result"] == "Pass"  # audit chain intact
    assert res["CTL-04"]["result"] == "Fail"  # TM and adverse media revalidations overdue
    assert {e["item"] for e in res["CTL-04"]["exception_items"]} == {"MDL-TM-001", "MDL-AM-006"}
    assert res["CTL-08"]["exceptions"] == 3  # overdue findings


def test_control_maintenance_and_evidence(client, auth):
    assert client.patch("/api/v1/regulatory/controls/CTL-20", json={"implementation_status": "Implemented"},
                        headers=auth("jpatel")).status_code == 403
    r = client.patch("/api/v1/regulatory/controls/CTL-20", json={
        "implementation_status": "Partially implemented", "remediation_actions": "Pilot cohort trained 20 Nov"},
        headers=auth("lferreira"))
    assert r.status_code == 200 and r.json()["implementation_status"] == "Partially implemented"
    ev = client.post("/api/v1/regulatory/controls/CTL-20/evidence",
                     data={"title": "Training attendance", "evidence_type": "Training records"},
                     files={"file": ("attendance.csv", b"user,completed\nnbrooks,2026-11-20\n", "text/csv")},
                     headers=auth("lferreira"))
    assert ev.status_code == 201
    detail = client.get("/api/v1/regulatory/controls/CTL-20", headers=auth("jpatel")).json()
    assert detail["evidence"][0]["evidence_id"] == ev.json()["evidence_id"]
    hist = client.get("/api/v1/audit/events", params={"entity_type": "control", "entity_ref": "CTL-20"},
                      headers=auth("hmarsh")).json()
    assert {e["action"] for e in hist["items"]} >= {"CONTROL_UPDATED", "EVIDENCE_ADDED"}
