"""End-to-end workflow across modules, through the API only:

drift appears -> monitoring raises a breach -> owner acknowledges -> validator raises a finding during the
in-flight validation -> validation is conditionally approved -> owner remediates with evidence -> an
independent validator closes the finding -> committee report reflects it -> control tests run -> the audit
chain verifies and contains every step in order.
"""
from __future__ import annotations

import io

from pypdf import PdfReader


def test_drift_to_remediation_to_committee_report(client, auth):
    H = auth  # noqa: N806
    start_audit = client.get("/api/v1/audit/events", params={"page_size": 1}, headers=H("admin")).json()["items"][0]["id"]

    # 1. A severe drift month arrives and monitoring flags the transaction monitoring model
    sim = client.post("/api/v1/monitoring/simulate", json={"scenario": "severe"}, headers=H("admin"))
    assert sim.status_code == 200, sim.text
    period = sim.json()["period"]
    assert "MDL-TM-001" in sim.json()["models_in_breach"]
    breaches = client.get("/api/v1/monitoring/breaches", params={"model_id": "MDL-TM-001", "period": period,
                                                                 "level": "Breach"}, headers=H("jpatel")).json()["items"]
    recall = next(b for b in breaches if b["metric"] == "recall")
    assert recall["value"] < recall["breach_limit"]

    # 2. The model owner acknowledges it
    r = client.post(f"/api/v1/monitoring/breaches/{recall['breach_id']}/acknowledge",
                    json={"notes": "Linked to scenario coverage gap; validation team informed"}, headers=H("jpatel"))
    assert r.json()["status"] == "Acknowledged"

    # 3. The in-flight periodic validation picks it up as a finding with evidence
    vid = next(v["validation_id"] for v in client.get("/api/v1/validations", params={"model_id": "MDL-TM-001"},
                                                      headers=H("nbrooks")).json() if v["status"] == "In Progress")
    f = client.post(f"/api/v1/validations/{vid}/findings", json={
        "title": "Recall breach under severe drift", "severity": "High", "category": "Performance",
        "description": f"Recall {recall['value']:.3f} in {period} fell below the {recall['breach_limit']} breach limit."},
        headers=H("nbrooks"))
    assert f.status_code == 201
    fid = f.json()["finding_id"]
    ev = client.post(f"/api/v1/validations/{vid}/evidence", data={"title": "Simulated month outcomes",
                     "evidence_type": "Back-testing data"},
                     files={"file": ("outcomes.csv", b"period,recall\n" + period.encode() + b",0.30\n", "text/csv")},
                     headers=H("tlindgren"))
    assert ev.status_code == 201
    client.patch(f"/api/v1/validations/{vid}", json={"overall_rating": "Needs improvement", "summary":
                 "Scenario logic is sound but recall degrades sharply when launderers move below the band and onto instant payments."},
                 headers=H("nbrooks"))
    assert client.post(f"/api/v1/validations/{vid}/transition", json={"to_status": "Pending Review"},
                       headers=H("nbrooks")).json()["status"] == "Pending Review"

    # 4. Approval: full approval blocked by the open High finding, conditional approval allowed
    assert client.post(f"/api/v1/validations/{vid}/transition", json={"to_status": "Approved"},
                       headers=H("hmarsh")).status_code == 422
    r = client.post(f"/api/v1/validations/{vid}/transition", json={
        "to_status": "Conditionally Approved", "comment": "Approved at MRMC",
        "conditions": f"Remediate {fid} within 90 days and report recall monthly to FCMOC."}, headers=H("hmarsh"))
    assert r.status_code == 200
    model = client.get("/api/v1/models/MDL-TM-001", headers=H("hmarsh")).json()
    assert model["approval_status"] == "Conditionally Approved" and model["validation_state"] == "Current"

    # 5. Remediation and independent closure
    owner_id = model["model_risk_owner"]["id"]
    client.post(f"/api/v1/findings/{fid}/response", json={
        "management_response": "Agreed; instant payments will be added to the rapid movement scenario.",
        "action_plan": "Extend scenario, lower structuring band, parallel run for one quarter.",
        "remediation_owner_id": owner_id, "target_date": "2027-02-15"}, headers=H("jpatel"))
    client.post(f"/api/v1/findings/{fid}/transition", json={"to_status": "In Remediation"}, headers=H("tlindgren"))
    client.post(f"/api/v1/findings/{fid}/evidence", data={"title": "Parallel run results", "evidence_type": "Test results"},
                files={"file": ("parallel.txt", b"recall restored to 0.61 in parallel run", "text/plain")}, headers=H("jpatel"))
    assert client.post(f"/api/v1/findings/{fid}/transition", json={"to_status": "Pending Validation"},
                       headers=H("jpatel")).json()["status"] == "Pending Validation"
    closed = client.post(f"/api/v1/findings/{fid}/transition", json={"to_status": "Closed", "comment": "Verified"},
                         headers=H("nbrooks")).json()
    assert closed["status"] == "Closed"
    assert [h["to_status"] for h in closed["history"] if h["event_type"] == "STATUS_CHANGE"] == [
        "In Remediation", "Pending Validation", "Closed"]

    # 6. Committee reporting reflects the new period and the decision
    rep = client.post("/api/v1/reports", json={"report_type": "executive"}, headers=H("hmarsh")).json()
    pdf = client.get(f"/api/v1/reports/{rep['report_id']}/download", headers=H("hmarsh")).content
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert vid in text and period in text

    # 7. Controls and audit trail
    tests = client.post("/api/v1/regulatory/controls/test", json={}, headers=H("hmarsh")).json()
    assert next(t for t in tests if t["control_id"] == "CTL-19")["result"] == "Pass"
    assert client.get("/api/v1/audit/verify", headers=H("hmarsh")).json()["valid"]
    events = client.get("/api/v1/audit/events", params={"page_size": 200}, headers=H("admin")).json()["items"]
    new = [e["action"] for e in reversed(events) if e["id"] > start_audit]
    expected = ["SIMULATION_RUN", "BREACH_ACKNOWLEDGED", "FINDING_RAISED", "EVIDENCE_ADDED", "VALIDATION_UPDATED",
                "VALIDATION_STATUS", "MODEL_APPROVAL_UPDATED", "VALIDATION_APPROVAL", "FINDING_RESPONSE",
                "FINDING_STATUS", "EVIDENCE_ADDED", "FINDING_STATUS", "FINDING_CLOSED", "REPORT_GENERATED",
                "CONTROL_TESTS_RUN"]
    it = iter(new)
    assert all(any(a == e for a in it) for e in expected), new
