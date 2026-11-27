from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.routes.validations import user_ref
from app.core.config import get_settings
from app.core.enums import AIApprovalStatus, Answer, EUAIActClass
from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.models.ai import (
    AIAssessment,
    AISystem,
    AssessmentQuestion,
    BiasTestResult,
    LLMEvalCase,
    LLMEvalResult,
    LLMEvalRun,
)
from app.models.users import User
from app.services import ai as svc

router = APIRouter(tags=["ai-governance"])


def system_out(db: Session, s: AISystem, user: User, full: bool = False):
    latest_a = db.execute(select(AIAssessment).where(AIAssessment.ai_system_id == s.id)
                          .order_by(AIAssessment.id.desc())).unique().scalars().first()
    ev = svc.latest_eval(db, s)
    d = {
        "system_id": s.system_id, "name": s.name, "use_case": s.use_case, "business_unit": s.business_unit,
        "business_justification": s.business_justification,
        "linked_model": {"model_id": s.linked_model.model_id, "name": s.linked_model.name} if s.linked_model else None,
        "model_owner": user_ref(s.model_owner), "system_owner": user_ref(s.system_owner),
        "ai_technique": s.ai_technique, "provider": s.provider, "deployment_status": s.deployment_status,
        "data_sources": s.data_sources, "intended_use": s.intended_use, "prohibited_use": s.prohibited_use,
        "affects_natural_persons": s.affects_natural_persons, "interacts_with_public": s.interacts_with_public,
        "human_oversight": s.human_oversight, "oversight_description": s.oversight_description,
        "explainability_rating": s.explainability_rating, "explainability_notes": s.explainability_notes,
        "bias_testing_status": s.bias_testing_status, "bias_testing_summary": s.bias_testing_summary,
        "performance_monitoring": s.performance_monitoring, "hallucination_evaluation": s.hallucination_evaluation,
        "limitations": s.limitations, "internal_risk_tier": s.internal_risk_tier,
        "eu_ai_act_class": s.eu_ai_act_class, "approval_status": s.approval_status, "approved_on": s.approved_on,
        "next_review_date": s.next_review_date,
        "latest_assessment": None if latest_a is None else {
            "assessment_id": latest_a.assessment_id, "status": latest_a.status,
            "overall_score": latest_a.overall_score, "derived_classification": latest_a.derived_classification,
            "gaps": len(latest_a.gaps or [])},
        "latest_evaluation": None if ev is None else {"run_id": ev.run_id, "model_version": ev.model_version,
                                                       "passed": ev.passed, "run_at": ev.run_at},
        "can_edit": svc.can_edit_system(user, s),
    }
    if full:
        d["assessments"] = [{"assessment_id": a.assessment_id, "status": a.status, "assessor": user_ref(a.assessor),
                             "reviewer": user_ref(a.reviewer), "overall_score": a.overall_score,
                             "derived_classification": a.derived_classification, "submitted_at": a.submitted_at,
                             "reviewed_at": a.reviewed_at}
                            for a in db.execute(select(AIAssessment).where(AIAssessment.ai_system_id == s.id)
                                                .order_by(AIAssessment.id.desc())).unique().scalars()]
        d["evaluations"] = [{"run_id": r.run_id, "model_version": r.model_version, "passed": r.passed,
                             "metrics": r.metrics, "threshold_results": r.threshold_results, "run_at": r.run_at,
                             "triggered_by": r.triggered_by}
                            for r in db.execute(select(LLMEvalRun).where(LLMEvalRun.ai_system_id == s.id)
                                                .order_by(LLMEvalRun.run_at.desc())).unique().scalars()]
        d["eval_versions"] = svc.versions(db, s)
        d["bias_tests"] = [{"attribute": b.attribute, "reference_group": b.reference_group, "groups": b.groups,
                            "min_impact_ratio": b.min_ratio, "min_fpr_ratio": b.min_fpr_ratio, "passed": b.passed,
                            "method": b.method, "periods": b.periods, "records": b.records, "run_at": b.run_at,
                            "run_by": b.run_by}
                           for b in db.execute(select(BiasTestResult).where(BiasTestResult.ai_system_id == s.id)
                                               .order_by(BiasTestResult.run_at.desc())).scalars()]
        d["bias_testable"] = bool(s.linked_model and s.linked_model.model_id in svc.BIAS_SOURCES)
    return d


@router.get("/ai/meta")
def meta(_: User = Depends(require("ai:read"))):
    return {"categories": svc.CATEGORIES, "answers": Answer.values(), "classifications": EUAIActClass.values(),
            "approval_statuses": AIApprovalStatus.values(),
            "deployment_statuses": ["Development", "Pilot", "Production", "Blocked", "Retired"],
            "oversight_models": ["Human-in-the-loop", "Human-on-the-loop", "Human-in-command"],
            "disclaimer": "Internal readiness self-assessment. Not a conformity assessment, legal opinion or "
                          "certification of compliance with the EU AI Act."}


@router.get("/ai/systems")
def list_systems(db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    return [system_out(db, s, user) for s in db.execute(select(AISystem).order_by(AISystem.system_id)).unique().scalars()]


class SystemIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    linked_model_id: Optional[str] = Field(None, pattern=r"^MDL-[A-Z]{2,4}-\d{3}$")
    use_case: str = Field(min_length=10, max_length=2000)
    business_justification: str = Field(min_length=10, max_length=2000)
    business_unit: str = Field(min_length=2, max_length=80)
    model_owner_id: int
    system_owner_id: int
    ai_technique: str = Field(min_length=3, max_length=80)
    provider: str = Field(min_length=2, max_length=80)
    deployment_status: str = Field("Development", pattern="^(Development|Pilot|Production|Blocked|Retired)$")
    data_sources: List[str] = Field(default_factory=list, max_length=20)
    intended_use: str = Field(min_length=10, max_length=2000)
    prohibited_use: str = Field(min_length=5, max_length=2000)
    affects_natural_persons: bool = True
    interacts_with_public: bool = False
    human_oversight: str = Field(pattern="^(Human-in-the-loop|Human-on-the-loop|Human-in-command|None)$")
    oversight_description: str = Field("", max_length=2000)
    explainability_rating: str = Field("Medium", pattern="^(High|Medium|Low)$")
    explainability_notes: str = Field("", max_length=2000)
    limitations: str = Field("", max_length=4000)
    internal_risk_tier: str = Field(pattern="^(High|Medium|Low)$")


@router.post("/ai/systems", status_code=201)
def create_system(body: SystemIn, db: Session = Depends(get_db), user: User = Depends(require("ai:edit"))):
    data = body.model_dump()
    data["linked_model_id"] = svc.linked_model_by_id(db, data["linked_model_id"])
    for k in ("model_owner_id", "system_owner_id"):
        if db.get(User, data[k]) is None:
            raise NotFound(f"{k}: user not found")
    s = svc.create_system(db, user, data)
    db.commit()
    return system_out(db, svc.get_system(db, s.system_id), user, full=True)


@router.get("/ai/systems/{system_id}")
def get_system(system_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    return system_out(db, svc.get_system(db, system_id), user, full=True)


class SystemPatch(BaseModel):
    use_case: Optional[str] = Field(None, min_length=10, max_length=2000)
    business_justification: Optional[str] = Field(None, max_length=2000)
    deployment_status: Optional[str] = Field(None, pattern="^(Development|Pilot|Production|Blocked|Retired)$")
    data_sources: Optional[List[str]] = Field(None, max_length=20)
    intended_use: Optional[str] = Field(None, max_length=2000)
    prohibited_use: Optional[str] = Field(None, max_length=2000)
    human_oversight: Optional[str] = Field(None, pattern="^(Human-in-the-loop|Human-on-the-loop|Human-in-command|None)$")
    oversight_description: Optional[str] = Field(None, max_length=2000)
    explainability_rating: Optional[str] = Field(None, pattern="^(High|Medium|Low)$")
    explainability_notes: Optional[str] = Field(None, max_length=2000)
    performance_monitoring: Optional[str] = Field(None, max_length=2000)
    limitations: Optional[str] = Field(None, max_length=4000)
    internal_risk_tier: Optional[str] = Field(None, pattern="^(High|Medium|Low)$")


@router.patch("/ai/systems/{system_id}")
def patch_system(system_id: str, body: SystemPatch, db: Session = Depends(get_db),
                 user: User = Depends(require("ai:edit"))):
    s = svc.get_system(db, system_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("deployment_status") in ("Pilot", "Production") and s.approval_status not in (
            "Approved", "Approved with Conditions") and changes.get("deployment_status") == "Production":
        raise Forbidden("Production deployment needs AI Governance Committee approval")
    svc.update_system(db, user, s, changes)
    db.commit()
    return system_out(db, s, user, full=True)


class DecisionIn(BaseModel):
    decision: str
    conditions: str = Field("", max_length=4000)


@router.post("/ai/systems/{system_id}/decision")
def decide(system_id: str, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    s = svc.get_system(db, system_id)
    svc.decide_system(db, user, s, body.decision, body.conditions, get_settings().today())
    db.commit()
    return system_out(db, s, user, full=True)


def assessment_out(db: Session, a: AIAssessment, user: User):
    qs = list(db.execute(select(AssessmentQuestion).where(AssessmentQuestion.template_id == a.template_id)
                         .order_by(AssessmentQuestion.order)).scalars())
    ans = {r.question_id: r for r in a.responses}
    return {
        "assessment_id": a.assessment_id, "status": a.status,
        "system": {"system_id": a.ai_system.system_id, "name": a.ai_system.name},
        "template": {"name": a.template.name, "version": a.template.version, "framework": a.template.framework},
        "assessor": user_ref(a.assessor), "reviewer": user_ref(a.reviewer), "submitted_at": a.submitted_at,
        "reviewed_at": a.reviewed_at, "review_comments": a.review_comments,
        "derived_classification": a.derived_classification, "category_scores": a.category_scores,
        "overall_score": a.overall_score, "gaps": a.gaps,
        "questions": [{"question_id": q.id, "code": q.code, "category": q.category, "text": q.text,
                       "guidance": q.guidance, "reference": q.reference, "classification_trigger": q.classification_trigger,
                       "is_active": q.is_active,
                       "answer": ans[q.id].answer if q.id in ans else None,
                       "evidence_note": ans[q.id].evidence_note if q.id in ans else ""} for q in qs if q.is_active],
        "can_edit": a.status in ("Draft", "Returned") and (user.id == a.assessor_id or user.role == "admin"),
        "can_review": a.status == "Submitted" and user.role in ("compliance_reviewer", "admin")
        and user.id != a.assessor_id,
        "disclaimer": "Internal readiness self-assessment, not a conformity assessment or legal determination.",
    }


@router.post("/ai/systems/{system_id}/assessments", status_code=201)
def start_assessment(system_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:assess"))):
    a = svc.start_assessment(db, user, svc.get_system(db, system_id))
    db.commit()
    return assessment_out(db, svc.get_assessment(db, a.assessment_id), user)


@router.get("/ai/assessments/{assessment_id}")
def get_assessment(assessment_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    return assessment_out(db, svc.get_assessment(db, assessment_id), user)


class ResponseItem(BaseModel):
    question_id: int
    answer: str
    evidence_note: str = Field("", max_length=2000)


class ResponsesIn(BaseModel):
    items: List[ResponseItem] = Field(min_length=1, max_length=100)


@router.put("/ai/assessments/{assessment_id}/responses")
def save_responses(assessment_id: str, body: ResponsesIn, db: Session = Depends(get_db),
                   user: User = Depends(require("ai:assess"))):
    a = svc.get_assessment(db, assessment_id)
    svc.save_responses(db, user, a, [i.model_dump() for i in body.items])
    db.commit()
    return assessment_out(db, a, user)


@router.post("/ai/assessments/{assessment_id}/submit")
def submit(assessment_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:assess"))):
    a = svc.get_assessment(db, assessment_id)
    svc.submit_assessment(db, user, a)
    db.commit()
    return assessment_out(db, a, user)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(Approved|Returned)$")
    comments: str = Field("", max_length=4000)


@router.post("/ai/assessments/{assessment_id}/review")
def review(assessment_id: str, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    a = svc.get_assessment(db, assessment_id)
    svc.review_assessment(db, user, a, body.decision, body.comments)
    db.commit()
    db.refresh(a)
    return assessment_out(db, a, user)


@router.get("/ai/templates/active")
def template(db: Session = Depends(get_db), _: User = Depends(require("ai:read"))):
    t = svc.active_template(db)
    return {"id": t.id, "name": t.name, "version": t.version, "framework": t.framework,
            "description": t.description,
            "questions": [{"id": q.id, "code": q.code, "category": q.category, "text": q.text,
                           "reference": q.reference, "weight": q.weight, "classification_trigger":
                           q.classification_trigger, "is_active": q.is_active} for q in t.questions]}


class QuestionIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z]{2}-\d{2}$")
    category: str
    text: str = Field(min_length=15, max_length=1000)
    guidance: str = Field("", max_length=2000)
    reference: str = Field(min_length=3, max_length=120)
    weight: float = Field(1.0, ge=0.1, le=5)
    classification_trigger: Optional[str] = None


@router.post("/ai/templates/questions", status_code=201)
def add_question(body: QuestionIn, db: Session = Depends(get_db), user: User = Depends(require("ai:template_edit"))):
    q = svc.add_question(db, user, body.model_dump())
    db.commit()
    return {"id": q.id, "code": q.code, "template_version": q.template.version}


class ActiveIn(BaseModel):
    is_active: bool


@router.patch("/ai/templates/questions/{question_id}")
def toggle_question(question_id: int, body: ActiveIn, db: Session = Depends(get_db),
                    user: User = Depends(require("ai:template_edit"))):
    q = db.get(AssessmentQuestion, question_id)
    if q is None:
        raise NotFound("Question not found")
    svc.set_question_active(db, user, q, body.is_active)
    db.commit()
    return {"id": q.id, "is_active": q.is_active, "template_version": q.template.version}


@router.get("/ai/eval/cases")
def eval_cases(system_id: Optional[str] = Query(None, max_length=16), db: Session = Depends(get_db),
               _: User = Depends(require("ai:read"))):
    stmt = select(LLMEvalCase, AISystem.system_id).join(AISystem, LLMEvalCase.ai_system_id == AISystem.id)
    if system_id:
        stmt = stmt.where(AISystem.system_id == system_id)
    return [{"case_id": c.case_id, "system_id": sid, "category": c.category, "prompt": c.prompt, "context": c.context,
             "expected_behavior": c.expected_behavior, "expected_facts": c.expected_facts,
             "allowed_references": c.allowed_references, "consistency_group": c.consistency_group}
            for c, sid in db.execute(stmt.order_by(LLMEvalCase.case_id)).all()]


class EvalIn(BaseModel):
    system_id: str = Field(max_length=16)
    model_version: str = Field(max_length=32)


@router.post("/ai/eval/runs", status_code=201)
def run_eval(body: EvalIn, db: Session = Depends(get_db), user: User = Depends(require("ai:eval_run"))):
    run = svc.run_evaluation(db, (user.username, user.role), svc.get_system(db, body.system_id), body.model_version)
    db.commit()
    return eval_detail(run.run_id, db, user)


@router.get("/ai/eval/runs/{run_id}")
def eval_detail(run_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:read"))):
    r = db.execute(select(LLMEvalRun).where(LLMEvalRun.run_id == run_id)).unique().scalar_one_or_none()
    if r is None:
        raise NotFound("Evaluation run not found")
    results = db.execute(select(LLMEvalResult).where(LLMEvalResult.run_id == r.id)).unique().scalars()
    return {"run_id": r.run_id, "system_id": r.ai_system.system_id, "system_name": r.ai_system.name,
            "model_version": r.model_version, "case_count": r.case_count, "metrics": r.metrics,
            "threshold_results": r.threshold_results, "passed": r.passed, "run_at": r.run_at,
            "triggered_by": r.triggered_by,
            "results": sorted([{"case_id": x.case.case_id, "category": x.case.category, "prompt": x.case.prompt,
                                "response": x.response_text, "facts_expected": x.facts_expected,
                                "facts_found": x.facts_found, "claims": x.claims_total,
                                "unsupported_claims": x.unsupported_claims,
                                "hallucinated_references": x.hallucinated_references,
                                "policy_violations": x.policy_violations, "behavior_correct": x.behavior_correct,
                                "normalized_answer": x.normalized_answer, "reviewer_decision": x.reviewer_decision,
                                "passed": x.passed} for x in results], key=lambda d: d["case_id"]),
            "disclaimer": "Deterministic tests on recorded responses. Not a certification."}


@router.post("/ai/systems/{system_id}/bias-test", status_code=201)
def bias_test(system_id: str, db: Session = Depends(get_db), user: User = Depends(require("ai:bias_test"))):
    svc.run_bias_test(db, (user.username, user.role), svc.get_system(db, system_id))
    db.commit()
    return system_out(db, svc.get_system(db, system_id), user, full=True)

