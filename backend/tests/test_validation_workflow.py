"""Milestone 4: validation workflow, independence rules, evidence, findings lifecycle and overdue tracking."""
from __future__ import annotations

import hashlib

from tests.conftest import TEST_PASSWORD  # noqa: F401


def _uid(client, auth, username):
    return next(u["id"] for u in client.get("/api/v1/users", headers=auth("admin")).json() if u["username"] == username)


def test_seeded_validations_cover_every_status(client, auth):
    vs = client.get("/api/v1/validations", headers=auth("hmarsh")).json()
    statuses = {v["status"] for v in vs}
    assert statuses == {"Not Started", "Scheduled", "In Progress", "Pending Review", "Approved",
                        "Conditionally Approved", "Rejected"}
    assert len(vs) == 12
    findings = client.get("/api/v1/findings", headers=auth("hmarsh")).json()
    assert len(findings) >= 25


def test_overdue_tracking(client, auth):
    s = client.get("/api/v1/findings/summary", headers=auth("hmarsh")).json()
    overdue = client.get("/api/v1/findings", params={"overdue": True}, headers=auth("hmarsh")).json()
    assert s["overdue"] == len(overdue) == 3
    assert all(f["overdue"] and f["days_overdue"] > 0 for f in overdue)
    assert {f["severity"] for f in overdue} == {"Critical", "High", "Medium"}
    assert sum(s["aging"].values()) == s["open"]


def test_finding_history_is_ordered(client, auth):
    closed = next(f for f in client.get("/api/v1/findings", params={"status": "Closed"}, headers=auth("nbrooks")).json()
                  if f["severity"] == "High")
    detail = client.get(f"/api/v1/findings/{closed['finding_id']}", headers=auth("nbrooks")).json()
    statuses = [h["to_status"] for h in detail["history"] if h["to_status"]]
    assert statuses == ["Open", "Response Submitted", "In Remediation", "Pending Validation", "Closed"]
    assert detail["evidence"] and detail["evidence"][0]["sha256"]


def test_independence_rules(client, auth):
    owner = _uid(client, auth, "skim")
    jp = _uid(client, auth, "jpatel")
    r = client.post("/api/v1/validations", json={"model_id": "MDL-PEP-005", "validation_type": "Change / Targeted",
                                                 "lead_validator_id": jp}, headers=auth("hmarsh"))
    assert r.status_code == 422 and "not a validator" in r.json()["error"]["message"]
    assert client.post("/api/v1/validations", json={"model_id": "MDL-PEP-005", "validation_type": "Periodic"},
                       headers=auth("nbrooks")).status_code == 403  # validators do not schedule themselves
    # one active validation per model
    r = client.post("/api/v1/validations", json={"model_id": "MDL-TM-001", "validation_type": "Change / Targeted"},
                    headers=auth("hmarsh"))
    assert r.status_code == 409
    assert owner  # owner id resolved


def test_full_validation_and_remediation_lifecycle(client, auth, db):
    tl = _uid(client, auth, "tlindgren")
    gw = _uid(client, auth, "gwu")
    ew = _uid(client, auth, "ewalsh")
    H = auth  # noqa: N806

    r = client.post("/api/v1/validations", json={
        "model_id": "MDL-PEP-005", "validation_type": "Change / Targeted",
        "scope_areas": ["Conceptual soundness", "Outcomes analysis and back-testing"],
        "scope_notes": "Targeted review of the transliteration library upgrade.",
        "lead_validator_id": tl, "team": [gw], "scheduled_start": "2026-11-20", "scheduled_end": "2026-12-20"},
        headers=H("hmarsh"))
    assert r.status_code == 201, r.text
    vid = r.json()["validation_id"]
    assert r.json()["status"] == "Not Started"

    t = lambda who, to, **kw: client.post(f"/api/v1/validations/{vid}/transition",  # noqa: E731
                                          json={"to_status": to, **kw}, headers=H(who))
    assert t("hmarsh", "Scheduled").status_code == 200
    # lead must attest independence before starting
    r = t("tlindgren", "In Progress")
    assert r.status_code == 422 and "attest" in r.json()["error"]["message"]
    assert t("gwu", "In Progress").status_code == 403  # only the lead starts fieldwork
    r = client.patch(f"/api/v1/validations/{vid}", json={"independence_attested": True,
                     "independence_statement": "No involvement in PEP model development or use."}, headers=H("tlindgren"))
    assert r.status_code == 200
    assert t("tlindgren", "In Progress").json()["status"] == "In Progress"

    # submission prerequisites
    r = t("tlindgren", "Pending Review")
    assert r.status_code == 422 and "evidence" in r.json()["error"]["message"]

    # evidence upload: wrong type rejected, CSV accepted and hash recorded
    bad = client.post(f"/api/v1/validations/{vid}/evidence", data={"title": "Script", "evidence_type": "Code"},
                      files={"file": ("run.sh", b"echo hi", "application/x-sh")}, headers=H("tlindgren"))
    assert bad.status_code == 422
    content = b"name,score,true_match\nUmar Haddad,0.91,1\n"
    ev = client.post(f"/api/v1/validations/{vid}/evidence",
                     data={"title": "Transliteration test deck results", "evidence_type": "Test results"},
                     files={"file": ("deck.csv", content, "text/csv")}, headers=H("gwu"))
    assert ev.status_code == 201, ev.text
    assert ev.json()["sha256"] == hashlib.sha256(content).hexdigest()
    dl = client.get(f"/api/v1/evidence/{ev.json()['evidence_id']}/download", headers=H("hmarsh"))
    assert dl.status_code == 200 and dl.content == content

    # raise a High finding
    f = client.post(f"/api/v1/validations/{vid}/findings", json={
        "title": "Upgrade drops two transliteration pairs", "severity": "High", "category": "Implementation",
        "description": "Regression testing found two transliteration pairs missing after the library upgrade."},
        headers=H("gwu"))
    assert f.status_code == 201, f.text
    fid = f.json()["finding_id"]
    assert f.json()["remediation_owner"]["username"] == "ewalsh"  # defaults to model risk owner

    client.patch(f"/api/v1/validations/{vid}", json={"overall_rating": "Needs improvement",
                 "summary": "The upgrade improves recall on most variants but two transliteration pairs regressed."},
                 headers=H("tlindgren"))
    assert t("tlindgren", "Pending Review").json()["status"] == "Pending Review"

    # approval rules
    assert t("tlindgren", "Approved").status_code == 403  # validators cannot approve
    assert t("skim", "Approved").status_code == 403  # owners cannot approve
    r = t("hmarsh", "Approved")
    assert r.status_code == 422 and fid in r.json()["error"]["details"]["findings"]
    r = t("hmarsh", "Conditionally Approved", conditions="too short")
    assert r.status_code == 422

    # finding lifecycle
    ft = lambda who, to, **kw: client.post(f"/api/v1/findings/{fid}/transition",  # noqa: E731
                                           json={"to_status": to, **kw}, headers=H(who))
    assert client.post(f"/api/v1/findings/{fid}/response", json={
        "management_response": "Agreed, pairs dropped in the vendor package.",
        "action_plan": "Restore the pairs and add a regression test to the deployment checklist.",
        "remediation_owner_id": ew, "target_date": "2026-12-15"}, headers=H("jpatel")).status_code == 403
    r = client.post(f"/api/v1/findings/{fid}/response", json={
        "management_response": "Agreed, pairs dropped in the vendor package.",
        "action_plan": "Restore the pairs and add a regression test to the deployment checklist.",
        "remediation_owner_id": ew, "target_date": "2026-12-15"}, headers=H("ewalsh"))
    assert r.status_code == 200 and r.json()["status"] == "Response Submitted"
    assert ft("nbrooks", "Open").status_code == 422  # rejecting needs a reason
    assert ft("tlindgren", "In Remediation").json()["status"] == "In Remediation"
    r = ft("ewalsh", "Pending Validation")
    assert r.status_code == 422 and "evidence" in r.json()["error"]["message"]
    client.post(f"/api/v1/findings/{fid}/evidence", data={"title": "Regression test output", "evidence_type": "Test results"},
                files={"file": ("regression.txt", b"all 412 pairs present", "text/plain")}, headers=H("ewalsh"))
    assert ft("ewalsh", "Pending Validation").json()["status"] == "Pending Validation"
    assert ft("ewalsh", "Closed").status_code == 403  # remediator cannot close
    closed = ft("gwu", "Closed", comment="Re-ran deck; both pairs restored")
    assert closed.json()["status"] == "Closed" and closed.json()["closed_by"]["username"] == "gwu"

    # now full approval is allowed and updates the inventory
    r = t("hmarsh", "Approved", comment="Approved at committee")
    assert r.status_code == 200, r.text
    model = client.get("/api/v1/models/MDL-PEP-005", headers=H("hmarsh")).json()
    assert model["approval_status"] == "Approved"
    assert model["last_validation_date"] == "2026-11-25"
    assert model["next_validation_date"] == "2028-11-25"  # Medium risk: 24-month cycle
    hist = client.get(f"/api/v1/validations/{vid}", headers=H("hmarsh")).json()["history"]
    moves = [h["to_status"] for h in hist if h["event_type"] in ("CREATED", "STATUS_CHANGE")]
    assert moves == ["Not Started", "Scheduled", "In Progress", "Pending Review", "Approved"]


def test_risk_acceptance_and_extension_rules(client, auth):
    findings = client.get("/api/v1/findings", params={"open_only": True}, headers=auth("hmarsh")).json()
    critical = next(f for f in findings if f["severity"] == "Critical" and f["status"] == "Open")
    r = client.post(f"/api/v1/findings/{critical['finding_id']}/transition", json={
        "to_status": "Risk Accepted", "comment": "Business accepts the residual risk for now",
        "risk_acceptance_expiry": "2027-03-01"}, headers=auth("hmarsh"))
    assert r.status_code == 422 and "Critical" in r.json()["error"]["message"]
    medium = next(f for f in findings if f["severity"] == "Medium" and f["status"] == "Open")
    r = client.post(f"/api/v1/findings/{medium['finding_id']}/transition", json={
        "to_status": "Risk Accepted", "comment": "Accepted", "risk_acceptance_expiry": "2027-03-01"},
        headers=auth("hmarsh"))
    assert r.status_code == 422  # rationale too short
    r = client.post(f"/api/v1/findings/{medium['finding_id']}/transition", json={
        "to_status": "Risk Accepted", "comment": "Compensating manual review of all EDD referrals covers the gap",
        "risk_acceptance_expiry": "2027-05-01"}, headers=auth("hmarsh"))
    assert r.status_code == 200 and r.json()["status"] == "Risk Accepted"

    overdue = client.get("/api/v1/findings", params={"overdue": True}, headers=auth("hmarsh")).json()[0]
    assert client.post(f"/api/v1/findings/{overdue['finding_id']}/extend", json={
        "new_target_date": "2027-01-31", "justification": "Vendor release slipped to January"},
        headers=auth("jpatel")).status_code == 403
    r = client.post(f"/api/v1/findings/{overdue['finding_id']}/extend", json={
        "new_target_date": "2027-01-31", "justification": "Vendor release slipped to January; interim control in place"},
        headers=auth("dosei"))
    assert r.status_code == 200 and r.json()["overdue"] is False
    assert r.json()["extension_count"] >= 1


def test_audit_records_workflow(client, auth):
    ev = client.get("/api/v1/audit/events", params={"action": "VALIDATION_APPROVAL"}, headers=auth("hmarsh")).json()
    assert ev["total"] >= 1
    assert client.get("/api/v1/audit/verify", headers=auth("hmarsh")).json()["valid"]
