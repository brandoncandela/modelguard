"""Milestone 5: AI system inventory, EU AI Act readiness workflow, evaluation runs and approvals."""
from __future__ import annotations


def test_inventory_and_classifications(client, auth):
    systems = {s["system_id"]: s for s in client.get("/api/v1/ai/systems", headers=auth("lferreira")).json()}
    assert len(systems) == 10
    assert systems["AI-010"]["eu_ai_act_class"].startswith("Prohibited")
    assert systems["AI-010"]["approval_status"] == "Rejected"
    assert systems["AI-009"]["latest_assessment"]["derived_classification"].startswith("High-risk")
    assert systems["AI-005"]["bias_testing_status"] == "Passed"
    detail = client.get("/api/v1/ai/systems/AI-002", headers=auth("lferreira")).json()
    assert {e["model_version"] for e in detail["evaluations"]} == {"v1.2", "v1.3-rc"}


def test_complete_assessment_workflow(client, auth):
    a_id = client.get("/api/v1/ai/systems/AI-006", headers=auth("bcarter")).json()["latest_assessment"]["assessment_id"]
    a = client.get(f"/api/v1/ai/assessments/{a_id}", headers=auth("bcarter")).json()
    assert a["status"] == "Draft" and a["can_edit"]
    # submitting early fails: questions unanswered
    r = client.post(f"/api/v1/ai/assessments/{a_id}/submit", headers=auth("bcarter"))
    assert r.status_code == 422 and "unanswered" in r.json()["error"]["message"]
    items = []
    for q in a["questions"]:
        if q["category"] == "Risk classification":
            items.append({"question_id": q["question_id"], "answer": "Yes" if q["code"] in ("RC-06", "RC-07") else "No"})
        elif q["code"] in ("AR-02", "MA-03"):
            items.append({"question_id": q["question_id"], "answer": "No" if q["code"] == "AR-02" else "N/A"})
        else:
            items.append({"question_id": q["question_id"], "answer": "Yes", "evidence_note": "Drafting pack v0.3"})
    # evidence is required for Yes answers
    bad = [dict(items[-1], evidence_note="")]
    assert client.put(f"/api/v1/ai/assessments/{a_id}/responses", json={"items": bad},
                      headers=auth("bcarter")).status_code == 422
    assert client.put(f"/api/v1/ai/assessments/{a_id}/responses", json={"items": items},
                      headers=auth("nbrooks")).status_code == 403
    r = client.put(f"/api/v1/ai/assessments/{a_id}/responses", json={"items": items}, headers=auth("bcarter"))
    assert r.status_code == 200
    body = r.json()
    assert body["derived_classification"].startswith("Transparency")
    assert [g["code"] for g in body["gaps"]] == ["AR-02"]
    assert body["category_scores"]["Accuracy and robustness"] < 100
    assert client.post(f"/api/v1/ai/assessments/{a_id}/submit", headers=auth("bcarter")).json()["status"] == "Submitted"
    # the assessor cannot review; a model owner cannot review
    assert client.post(f"/api/v1/ai/assessments/{a_id}/review", json={"decision": "Approved"},
                       headers=auth("bcarter")).status_code == 403
    assert client.post(f"/api/v1/ai/assessments/{a_id}/review", json={"decision": "Returned", "comments": "short"},
                       headers=auth("lferreira")).status_code == 422
    r = client.post(f"/api/v1/ai/assessments/{a_id}/review", json={"decision": "Approved", "comments": "Agreed"},
                    headers=auth("lferreira"))
    assert r.status_code == 200
    s = client.get("/api/v1/ai/systems/AI-006", headers=auth("lferreira")).json()
    assert s["eu_ai_act_class"].startswith("Transparency")
    # generative system with no evaluation run cannot be approved
    r = client.post("/api/v1/ai/systems/AI-006/decision",
                    json={"decision": "Approved with Conditions", "conditions": "Investigator authorship required"},
                    headers=auth("lferreira"))
    assert r.status_code == 422 and "evaluation" in r.json()["error"]["message"]


def test_system_decision_rules(client, auth):
    r = client.post("/api/v1/ai/systems/AI-009/decision", json={"decision": "Approved"}, headers=auth("lferreira"))
    assert r.status_code == 422 and "approved EU AI Act" in r.json()["error"]["message"]
    r = client.post("/api/v1/ai/systems/AI-010/decision", json={"decision": "Approved"}, headers=auth("hmarsh"))
    assert r.status_code == 422 and "prohibited" in r.json()["error"]["message"]
    r = client.post("/api/v1/ai/systems/AI-002/decision", json={"decision": "Approved"}, headers=auth("cmorgan"))
    assert r.status_code == 403
    r = client.post("/api/v1/ai/systems/AI-002/decision", json={"decision": "Approved"}, headers=auth("lferreira"))
    assert r.status_code == 200 and r.json()["approval_status"] == "Approved"  # latest eval (v1.3-rc) passed


def test_evaluation_run_and_permissions(client, auth):
    assert client.post("/api/v1/ai/eval/runs", json={"system_id": "AI-002", "model_version": "v1.2"},
                       headers=auth("bcarter")).status_code == 403
    r = client.post("/api/v1/ai/eval/runs", json={"system_id": "AI-002", "model_version": "v1.2"}, headers=auth("gwu"))
    assert r.status_code == 201
    body = r.json()
    assert body["passed"] is False
    breached = {t["metric"] for t in body["threshold_results"] if t["status"] == "Breach"}
    assert {"hallucination_rate", "response_consistency"} <= breached
    r04 = next(x for x in body["results"] if x["case_id"] == "R04")
    assert r04["hallucinated_references"] == ["31 CFR 1020.877"]
    assert client.post("/api/v1/ai/eval/runs", json={"system_id": "AI-002", "model_version": "v9"},
                       headers=auth("gwu")).status_code == 422


def test_template_is_configurable(client, auth):
    t = client.get("/api/v1/ai/templates/active", headers=auth("hmarsh")).json()
    before = t["version"]
    q = {"code": "TR-04", "category": "Transparency", "reference": "AI-POL-002 §8.3",
         "text": "Are customers told how to reach a human when an AI system is involved?"}
    assert client.post("/api/v1/ai/templates/questions", json=q, headers=auth("jpatel")).status_code == 403
    r = client.post("/api/v1/ai/templates/questions", json=q, headers=auth("hmarsh"))
    assert r.status_code == 201 and r.json()["template_version"] != before
    assert client.post("/api/v1/ai/templates/questions", json=q, headers=auth("hmarsh")).status_code == 409


def test_bias_test_endpoint(client, auth):
    r = client.post("/api/v1/ai/systems/AI-005/bias-test", headers=auth("nbrooks"))
    assert r.status_code == 201
    latest = r.json()["bias_tests"][0]
    assert latest["records"] > 0 and latest["groups"]
    assert client.post("/api/v1/ai/systems/AI-002/bias-test", headers=auth("nbrooks")).status_code == 422
