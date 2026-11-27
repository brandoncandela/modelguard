"""Milestone 2: inventory CRUD, search and filters, archiving, ownership rules and audit history."""
from __future__ import annotations

NEW_MODEL = {
    "model_id": "MDL-TBM-011",
    "name": "Trade-Based ML Red Flag Scoring",
    "description": "Scores trade finance transactions for trade-based money laundering red flags.",
    "business_owner_id": None,
    "model_risk_owner_id": None,
    "business_unit": "Trade Finance Compliance",
    "category": "Transaction Monitoring",
    "methodology": "Rules on price variance, shipping route risk and invoice anomalies with weighted scoring.",
    "methodology_type": "Rules-based",
    "geographies": ["United States", "Singapore"],
    "risk_rating": "Medium",
    "lifecycle_stage": "Development",
    "documentation_checklist": {"Model development document": True, "Methodology and assumptions": True},
    "limitations": "No vessel tracking data; pricing benchmarks updated quarterly.",
}


def _user_id(client, auth, username):
    users = client.get("/api/v1/users", headers=auth("admin")).json()
    return next(u["id"] for u in users if u["username"] == username)


def test_login_and_me(client, auth):
    r = client.get("/api/v1/auth/me", headers=auth("nbrooks"))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "validator" and "finding:create" in body["permissions"]


def test_requires_token(client):
    r = client.get("/api/v1/models")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_bad_token_rejected(client):
    r = client.get("/api/v1/models", headers={"Authorization": "Bearer not.a.token"})
    assert r.status_code == 401


def test_list_has_ten_seeded_models(client, auth):
    r = client.get("/api/v1/models", headers=auth("hmarsh"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    ids = [m["model_id"] for m in body["items"]]
    assert ids == sorted(ids) and "MDL-COR-010" in ids
    tm = next(m for m in body["items"] if m["model_id"] == "MDL-TM-001")
    assert tm["validation_state"] == "Overdue"
    assert tm["documentation_completeness"] < 100


def test_search_and_filters(client, auth):
    h = auth("admin")
    r = client.get("/api/v1/models", params={"q": "sanctions"}, headers=h).json()
    assert {m["model_id"] for m in r["items"]} >= {"MDL-SF-002"}
    r = client.get("/api/v1/models", params={"q": "Sofia Kim"}, headers=h).json()  # owner name search
    assert {m["model_id"] for m in r["items"]} == {"MDL-SF-002", "MDL-NS-003", "MDL-PEP-005"}
    r = client.get("/api/v1/models", params=[("risk_rating", "High"), ("methodology_type", "x")], headers=h).json()
    assert all(m["risk_rating"] == "High" for m in r["items"]) and r["total"] == 6
    r = client.get("/api/v1/models", params={"validation_due": "overdue"}, headers=h).json()
    assert {m["model_id"] for m in r["items"]} == {"MDL-TM-001", "MDL-AM-006"}
    r = client.get("/api/v1/models", params={"sort": "risk_rating", "direction": "desc"}, headers=h).json()
    assert r["items"][0]["risk_rating"] == "High" and r["items"][-1]["risk_rating"] == "Medium"


def test_create_validation_errors(client, auth):
    bad = dict(NEW_MODEL, model_id="bad-id", business_owner_id=1, model_risk_owner_id=1, risk_rating="Extreme")
    r = client.post("/api/v1/models", json=bad, headers=auth("admin"))
    assert r.status_code == 422
    fields = {tuple(d["loc"])[-1] for d in r.json()["error"]["details"]}
    assert {"model_id", "risk_rating"} <= fields


def test_validator_cannot_create(client, auth):
    r = client.post("/api/v1/models", json=NEW_MODEL, headers=auth("nbrooks"))
    assert r.status_code == 403


def test_owner_creates_edits_and_admin_archives(client, auth):
    jp = _user_id(client, auth, "jpatel")
    mr = _user_id(client, auth, "mreyes")
    body = dict(NEW_MODEL, business_owner_id=mr, model_risk_owner_id=jp)
    r = client.post("/api/v1/models", json=body, headers=auth("jpatel"))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["approval_status"] == "Pending Approval"
    assert created["documentation_status"] == "Incomplete"  # 2 of 6 artifacts
    assert created["can_edit"] is True

    # duplicate id
    assert client.post("/api/v1/models", json=body, headers=auth("jpatel")).status_code == 409

    # another owner cannot edit it
    r = client.patch("/api/v1/models/MDL-TBM-011", json={"version": "1.1"}, headers=auth("skim"))
    assert r.status_code == 403

    # owner cannot self-approve
    r = client.patch("/api/v1/models/MDL-TBM-011", json={"approval_status": "Approved"}, headers=auth("jpatel"))
    assert r.status_code == 403

    # owner edit: rerating and documentation
    docs = {a: True for a in client.get("/api/v1/models/facets", headers=auth("jpatel")).json()["documentation_artifacts"]}
    r = client.patch("/api/v1/models/MDL-TBM-011", json={"risk_rating": "High", "documentation_checklist": docs},
                     headers=auth("jpatel"))
    assert r.status_code == 200, r.text
    assert r.json()["risk_rating"] == "High" and r.json()["documentation_status"] == "Complete"

    # owner cannot archive; admin can, with a reason
    assert client.post("/api/v1/models/MDL-TBM-011/archive", json={"reason": "Replaced by vendor module"},
                       headers=auth("jpatel")).status_code == 403
    r = client.post("/api/v1/models/MDL-TBM-011/archive", json={"reason": "Replaced by vendor TBML module"},
                    headers=auth("admin"))
    assert r.status_code == 200 and r.json()["is_archived"] is True
    listed = client.get("/api/v1/models", headers=auth("admin")).json()
    assert "MDL-TBM-011" not in {m["model_id"] for m in listed["items"]}
    archived = client.get("/api/v1/models", params={"archived_only": True}, headers=auth("admin")).json()
    assert [m["model_id"] for m in archived["items"]] == ["MDL-TBM-011"]
    # archived models are read-only
    r = client.patch("/api/v1/models/MDL-TBM-011", json={"version": "2.0"}, headers=auth("admin"))
    assert r.status_code == 422
    assert client.post("/api/v1/models/MDL-TBM-011/restore", headers=auth("admin")).status_code == 200

    history = client.get("/api/v1/models/MDL-TBM-011/history", headers=auth("hmarsh")).json()
    actions = [h["action"] for h in history]
    assert actions[:4] == ["MODEL_RESTORED", "MODEL_ARCHIVED", "MODEL_RISK_RERATED", "MODEL_CREATED"]
    rerate = history[2]["changes"]
    assert rerate["risk_rating"] == {"from": "Medium", "to": "High"}


def test_owner_must_be_model_owner_role(client, auth):
    val = _user_id(client, auth, "nbrooks")
    body = dict(NEW_MODEL, model_id="MDL-XYZ-099", business_owner_id=val, model_risk_owner_id=val)
    r = client.post("/api/v1/models", json=body, headers=auth("admin"))
    assert r.status_code == 422 and "model owners" in r.json()["error"]["message"]


def test_audit_chain_still_valid_after_changes(client, auth):
    r = client.get("/api/v1/audit/verify", headers=auth("hmarsh"))
    assert r.status_code == 200 and r.json()["valid"] is True
    assert client.get("/api/v1/audit/verify", headers=auth("jpatel")).status_code == 403


def test_lockout_after_failed_logins(client):
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"username": "cmorgan", "password": "wrong-password"})
        assert r.status_code == 401
    from tests.conftest import TEST_PASSWORD

    r = client.post("/api/v1/auth/login", json={"username": "cmorgan", "password": TEST_PASSWORD})
    assert r.status_code == 401 and "locked" in r.json()["error"]["message"]
