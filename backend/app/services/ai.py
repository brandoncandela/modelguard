"""Module D: AI system inventory, EU AI Act readiness assessments, LLM evaluation and bias testing.

The EU AI Act assessment is an internal readiness self-assessment. Its derived classification is the
bank's working view for governance; it is not a conformity assessment, a legal opinion or a
certification of compliance.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import bias as bias_an
from app.analytics import llm_eval
from app.analytics.breaches import evaluate
from app.core.enums import AIApprovalStatus, Answer, AssessmentStatus, EUAIActClass
from app.core.errors import Conflict, Forbidden, NotFound, WorkflowError
from app.models.ai import (
    AIAssessment,
    AISystem,
    AssessmentQuestion,
    AssessmentResponse,
    AssessmentTemplate,
    BiasTestResult,
    LLMEvalCase,
    LLMEvalResult,
    LLMEvalRun,
    LLMRecordedResponse,
)
from app.models.data import Application, Customer, ScoredRecord, SimulationPeriod, Transaction
from app.models.inventory import InventoryModel
from app.models.users import User
from app.services import audit
from app.services.inventory import add_months

CATEGORIES = ["Risk classification", "Transparency", "Human oversight", "Data governance",
              "Accuracy and robustness", "Record keeping", "Monitoring and accountability"]
CLASS_PRECEDENCE = [EUAIActClass.PROHIBITED.value, EUAIActClass.HIGH_RISK.value, EUAIActClass.TRANSPARENCY.value,
                    EUAIActClass.MINIMAL.value]
SCORE = {"Yes": 1.0, "Partial": 0.5, "No": 0.0}
EDITABLE_SYSTEM = ["name", "use_case", "business_justification", "business_unit", "model_owner_id", "system_owner_id",
                   "ai_technique", "provider", "deployment_status", "data_sources", "intended_use", "prohibited_use",
                   "affects_natural_persons", "interacts_with_public", "human_oversight", "oversight_description",
                   "explainability_rating", "explainability_notes", "performance_monitoring",
                   "hallucination_evaluation", "limitations", "internal_risk_tier", "linked_model_id"]


def get_system(db: Session, system_id: str) -> AISystem:
    s = db.execute(select(AISystem).where(AISystem.system_id == system_id)).unique().scalar_one_or_none()
    if s is None:
        raise NotFound(f"AI system {system_id} not found")
    return s


def can_edit_system(user: User, s: AISystem) -> bool:
    return user.role == "admin" or (user.role == "model_owner" and user.id in (s.model_owner_id, s.system_owner_id))


def active_template(db: Session) -> AssessmentTemplate:
    t = db.execute(select(AssessmentTemplate).where(AssessmentTemplate.is_active.is_(True))
                   .order_by(AssessmentTemplate.id.desc())).scalars().first()
    if t is None:
        raise WorkflowError("No active assessment template")
    return t


def create_system(db: Session, user: User, data: Dict[str, Any]) -> AISystem:
    n = db.execute(select(func.count()).select_from(AISystem)).scalar()
    sid = f"AI-{n + 1:03d}"
    if user.role == "model_owner" and user.id not in (data["model_owner_id"], data["system_owner_id"]):
        raise Forbidden("Model owners can only register AI systems they own")
    s = AISystem(system_id=sid, approval_status=AIApprovalStatus.DRAFT.value,
                 eu_ai_act_class=EUAIActClass.NOT_ASSESSED.value, **data)
    db.add(s)
    db.flush()
    audit.record(db, user.username, user.role, "AI_SYSTEM_REGISTERED", "ai_system", sid, f"Registered {s.name}",
                 {k: v for k, v in data.items() if k in ("use_case", "ai_technique", "internal_risk_tier")})
    return s


def update_system(db: Session, user: User, s: AISystem, changes: Dict[str, Any]) -> AISystem:
    if not can_edit_system(user, s):
        raise Forbidden("Only the system's owners or an administrator can edit it")
    before = {k: getattr(s, k) for k in changes if k in EDITABLE_SYSTEM}
    for k, v in changes.items():
        if k in EDITABLE_SYSTEM:
            setattr(s, k, v)
    delta = audit.diff(before, {k: getattr(s, k) for k in before})
    if delta:
        audit.record(db, user.username, user.role, "AI_SYSTEM_UPDATED", "ai_system", s.system_id,
                     f"Updated {', '.join(sorted(delta))}", delta)
    return s


# ---------------------------------------------------------------------------------------------
# EU AI Act readiness assessments
# ---------------------------------------------------------------------------------------------


def score_assessment(questions: List[AssessmentQuestion], answers: Dict[int, AssessmentResponse]) -> Dict[str, Any]:
    triggered = []
    cats: Dict[str, List[float]] = {}
    weights: Dict[str, List[float]] = {}
    gaps = []
    unanswered = 0
    for q in questions:
        if not q.is_active:
            continue
        r = answers.get(q.id)
        if r is None:
            unanswered += 1
            continue
        if q.category == "Risk classification":
            if q.classification_trigger and r.answer == Answer.YES.value:
                triggered.append(q.classification_trigger)
            continue
        if r.answer == Answer.NA.value:
            continue
        cats.setdefault(q.category, []).append(SCORE[r.answer] * q.weight)
        weights.setdefault(q.category, []).append(q.weight)
        if r.answer in (Answer.NO.value, Answer.PARTIAL.value):
            gaps.append({"code": q.code, "category": q.category, "question": q.text, "answer": r.answer,
                         "reference": q.reference, "note": r.evidence_note})
    category_scores = {c: round(100 * sum(cats[c]) / sum(weights[c]), 1) for c in cats if sum(weights[c]) > 0}
    if unanswered and not triggered and not answers:
        derived = EUAIActClass.NOT_ASSESSED.value
    else:
        derived = next((c for c in CLASS_PRECEDENCE if c in triggered), EUAIActClass.MINIMAL.value)
    overall = round(sum(category_scores.values()) / len(category_scores), 1) if category_scores else None
    return {"category_scores": category_scores, "overall_score": overall, "derived_classification": derived,
            "gaps": gaps, "unanswered": unanswered, "triggers": triggered}


def _refresh_scores(db: Session, a: AIAssessment) -> Dict[str, Any]:
    qs = list(db.execute(select(AssessmentQuestion).where(AssessmentQuestion.template_id == a.template_id)
                         .order_by(AssessmentQuestion.order)).scalars())
    answers = {r.question_id: r for r in a.responses}
    res = score_assessment(qs, answers)
    a.category_scores = res["category_scores"]
    a.overall_score = res["overall_score"]
    a.derived_classification = res["derived_classification"]
    a.gaps = res["gaps"]
    return res


def start_assessment(db: Session, user: User, s: AISystem) -> AIAssessment:
    if not can_edit_system(user, s):
        raise Forbidden("Assessments are completed by the system's owners or an administrator")
    open_a = db.execute(select(AIAssessment.assessment_id).where(
        AIAssessment.ai_system_id == s.id, AIAssessment.status.in_(["Draft", "Submitted", "Returned"]))).scalar()
    if open_a:
        raise Conflict(f"Assessment {open_a} is already open for {s.system_id}")
    n = db.execute(select(func.count()).select_from(AIAssessment)).scalar()
    a = AIAssessment(assessment_id=f"AIA-{n + 1:04d}", ai_system_id=s.id, template_id=active_template(db).id,
                     status=AssessmentStatus.DRAFT.value, assessor_id=user.id)
    db.add(a)
    db.flush()
    audit.record(db, user.username, user.role, "AI_ASSESSMENT_STARTED", "ai_system", s.system_id,
                 f"Started EU AI Act readiness assessment {a.assessment_id}", {})
    return a


def get_assessment(db: Session, assessment_id: str) -> AIAssessment:
    a = db.execute(select(AIAssessment).where(AIAssessment.assessment_id == assessment_id)).unique().scalar_one_or_none()
    if a is None:
        raise NotFound(f"Assessment {assessment_id} not found")
    return a


def save_responses(db: Session, user: User, a: AIAssessment, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if a.status not in ("Draft", "Returned"):
        raise WorkflowError(f"Assessment is '{a.status}' and cannot be edited")
    if user.id != a.assessor_id and user.role != "admin":
        raise Forbidden("Only the assessor can answer this assessment")
    qs = {q.id: q for q in db.execute(select(AssessmentQuestion).where(
        AssessmentQuestion.template_id == a.template_id)).scalars()}
    existing = {r.question_id: r for r in a.responses}
    for it in items:
        q = qs.get(it["question_id"])
        if q is None:
            raise WorkflowError(f"Question {it['question_id']} is not in this assessment's template")
        if it["answer"] not in Answer.values():
            raise WorkflowError(f"{q.code}: answer must be one of {Answer.values()}")
        if it["answer"] in ("Yes", "Partial") and q.category != "Risk classification" and len(
                (it.get("evidence_note") or "").strip()) < 5:
            raise WorkflowError(f"{q.code}: describe the evidence for a '{it['answer']}' answer")
        r = existing.get(q.id)
        if r is None:
            r = AssessmentResponse(assessment_id=a.id, question_id=q.id, answer=it["answer"],
                                   evidence_note=it.get("evidence_note") or "")
            db.add(r)
            a.responses.append(r)
        else:
            r.answer = it["answer"]
            r.evidence_note = it.get("evidence_note") or ""
    db.flush()
    return _refresh_scores(db, a)


def submit_assessment(db: Session, user: User, a: AIAssessment) -> AIAssessment:
    if a.status not in ("Draft", "Returned"):
        raise WorkflowError(f"Only Draft or Returned assessments can be submitted (now '{a.status}')")
    if user.id != a.assessor_id and user.role != "admin":
        raise Forbidden("Only the assessor can submit")
    res = _refresh_scores(db, a)
    if res["unanswered"]:
        raise WorkflowError(f"{res['unanswered']} question(s) unanswered")
    frm = a.status
    a.status = AssessmentStatus.SUBMITTED.value
    a.submitted_at = datetime.now(timezone.utc)
    audit.record(db, user.username, user.role, "AI_ASSESSMENT_SUBMITTED", "ai_system", a.ai_system.system_id,
                 f"{a.assessment_id} submitted: {a.derived_classification}, readiness {a.overall_score}",
                 {"status": {"from": frm, "to": a.status}, "classification": a.derived_classification,
                  "gaps": len(a.gaps)})
    if a.ai_system.approval_status == AIApprovalStatus.DRAFT.value:
        a.ai_system.approval_status = AIApprovalStatus.UNDER_REVIEW.value
    return a


def review_assessment(db: Session, user: User, a: AIAssessment, decision: str, comments: str) -> AIAssessment:
    if a.status != AssessmentStatus.SUBMITTED.value:
        raise WorkflowError("Only submitted assessments can be reviewed")
    if user.role not in ("compliance_reviewer", "admin"):
        raise Forbidden("Assessments are reviewed by the AI governance reviewer")
    if user.id == a.assessor_id:
        raise Forbidden("The assessor cannot review their own assessment")
    if decision not in ("Approved", "Returned"):
        raise WorkflowError("decision must be Approved or Returned")
    if decision == "Returned" and len(comments.strip()) < 10:
        raise WorkflowError("Explain what must change (at least 10 characters)")
    s = a.ai_system
    a.status = decision
    a.reviewer_id = user.id
    a.reviewed_at = datetime.now(timezone.utc)
    a.review_comments = comments
    changes: Dict[str, Any] = {"status": {"from": "Submitted", "to": decision}}
    if decision == "Approved":
        old = s.eu_ai_act_class
        s.eu_ai_act_class = a.derived_classification
        changes["eu_ai_act_class"] = {"from": old, "to": s.eu_ai_act_class}
        if s.eu_ai_act_class == EUAIActClass.PROHIBITED.value:
            s.approval_status = AIApprovalStatus.REJECTED.value
            s.deployment_status = "Blocked"
            changes["approval_status"] = "Rejected automatically: prohibited practice"
    audit.record(db, user.username, user.role, "AI_ASSESSMENT_REVIEWED", "ai_system", s.system_id,
                 f"{a.assessment_id} {decision.lower()} by reviewer" + (f": {comments[:150]}" if comments else ""),
                 changes)
    return a


def latest_approved_assessment(db: Session, s: AISystem) -> Optional[AIAssessment]:
    return db.execute(select(AIAssessment).where(AIAssessment.ai_system_id == s.id,
                                                 AIAssessment.status == "Approved")
                      .order_by(AIAssessment.reviewed_at.desc(), AIAssessment.id.desc())).unique().scalars().first()


def latest_eval(db: Session, s: AISystem) -> Optional[LLMEvalRun]:
    return db.execute(select(LLMEvalRun).where(LLMEvalRun.ai_system_id == s.id)
                      .order_by(LLMEvalRun.run_at.desc(), LLMEvalRun.id.desc())).unique().scalars().first()


def decide_system(db: Session, user: User, s: AISystem, decision: str, conditions: str, today: date) -> AISystem:
    if user.role not in ("compliance_reviewer", "admin"):
        raise Forbidden("System approval is decided by the AI Governance Committee reviewer")
    if user.id in (s.model_owner_id, s.system_owner_id):
        raise Forbidden("Owners cannot approve their own AI system")
    allowed = [AIApprovalStatus.APPROVED.value, AIApprovalStatus.APPROVED_WITH_CONDITIONS.value,
               AIApprovalStatus.REJECTED.value, AIApprovalStatus.RETIRED.value]
    if decision not in allowed:
        raise WorkflowError(f"decision must be one of {allowed}")
    if decision in allowed[:2]:
        a = latest_approved_assessment(db, s)
        if a is None:
            raise WorkflowError("An approved EU AI Act readiness assessment is required first")
        if s.eu_ai_act_class == EUAIActClass.PROHIBITED.value:
            raise WorkflowError("Systems classified as a prohibited practice cannot be approved")
        if decision == AIApprovalStatus.APPROVED.value and s.eu_ai_act_class == EUAIActClass.HIGH_RISK.value and (
                a.overall_score or 0) < 80:
            raise WorkflowError("High-risk systems below 80% readiness can only be approved with conditions")
        if s.ai_technique.lower().startswith(("large language", "generative")):
            ev = latest_eval(db, s)
            if ev is None:
                raise WorkflowError("Generative systems need an LLM evaluation run before approval")
            if decision == AIApprovalStatus.APPROVED.value and not ev.passed:
                raise WorkflowError(f"Latest evaluation {ev.run_id} breached thresholds; approve with conditions "
                                    f"or remediate first")
        if decision == AIApprovalStatus.APPROVED_WITH_CONDITIONS.value and len(conditions.strip()) < 20:
            raise WorkflowError("Conditional approval needs written conditions (at least 20 characters)")
        s.approved_on = today
        s.next_review_date = add_months(today, 12)
    old = s.approval_status
    s.approval_status = decision
    audit.record(db, user.username, user.role, "AI_SYSTEM_DECISION", "ai_system", s.system_id,
                 f"{s.system_id} {old} to {decision}" + (f". Conditions: {conditions[:200]}" if conditions else ""),
                 {"approval_status": {"from": old, "to": decision}, "conditions": conditions})
    return s


def add_question(db: Session, user: User, data: Dict[str, Any]) -> AssessmentQuestion:
    t = active_template(db)
    if data["category"] not in CATEGORIES:
        raise WorkflowError(f"category must be one of {CATEGORIES}")
    if data.get("classification_trigger") and data["category"] != "Risk classification":
        raise WorkflowError("Only risk classification questions can set a classification")
    if data.get("classification_trigger") and data["classification_trigger"] not in CLASS_PRECEDENCE[:3]:
        raise WorkflowError(f"classification_trigger must be one of {CLASS_PRECEDENCE[:3]}")
    if db.execute(select(AssessmentQuestion.id).where(AssessmentQuestion.template_id == t.id,
                                                      AssessmentQuestion.code == data["code"])).first():
        raise Conflict(f"Question code {data['code']} already exists")
    order = (db.execute(select(func.max(AssessmentQuestion.order)).where(AssessmentQuestion.template_id == t.id))
             .scalar() or 0) + 1
    q = AssessmentQuestion(template_id=t.id, order=order, **data)
    db.add(q)
    major, minor = (t.version.split(".") + ["0"])[:2]
    t.version = f"{major}.{int(minor) + 1}"
    db.flush()
    audit.record(db, user.username, user.role, "AI_TEMPLATE_CHANGED", "assessment_template", str(t.id),
                 f"Added question {q.code} ({q.category}); template now v{t.version}",
                 {"code": q.code, "text": q.text, "reference": q.reference})
    return q


def set_question_active(db: Session, user: User, q: AssessmentQuestion, active: bool) -> AssessmentQuestion:
    q.is_active = active
    t = q.template
    major, minor = (t.version.split(".") + ["0"])[:2]
    t.version = f"{major}.{int(minor) + 1}"
    audit.record(db, user.username, user.role, "AI_TEMPLATE_CHANGED", "assessment_template", str(t.id),
                 f"{'Activated' if active else 'Deactivated'} question {q.code}; template now v{t.version}", {})
    return q


# ---------------------------------------------------------------------------------------------
# LLM evaluation
# ---------------------------------------------------------------------------------------------


def to_case(c: LLMEvalCase) -> llm_eval.Case:
    return llm_eval.Case(c.case_id, c.category, c.prompt, c.context, c.expected_behavior, list(c.expected_facts),
                         list(c.allowed_references), c.consistency_group, c.expected_answer_key)


def versions(db: Session, s: AISystem) -> List[str]:
    return sorted(set(db.execute(select(LLMRecordedResponse.model_version).join(
        LLMEvalCase, LLMRecordedResponse.case_id == LLMEvalCase.id).where(LLMEvalCase.ai_system_id == s.id)).scalars()))


def run_evaluation(db: Session, actor: tuple, s: AISystem, model_version: str,
                   run_at: Optional[datetime] = None) -> LLMEvalRun:
    cases = list(db.execute(select(LLMEvalCase).where(LLMEvalCase.ai_system_id == s.id)
                            .order_by(LLMEvalCase.case_id)).scalars())
    if not cases:
        raise WorkflowError(f"{s.system_id} has no evaluation cases")
    recorded = {r.case_id: r for r in db.execute(select(LLMRecordedResponse).where(
        LLMRecordedResponse.case_id.in_([c.id for c in cases]),
        LLMRecordedResponse.model_version == model_version)).scalars()}
    missing = [c.case_id for c in cases if c.id not in recorded]
    if missing:
        raise WorkflowError(f"No recorded responses for version '{model_version}'", {"missing_cases": missing})
    ecases = [to_case(c) for c in cases]
    results = [llm_eval.evaluate_case(ec, recorded[c.id].response_text, recorded[c.id].reviewer_decision)
               for ec, c in zip(ecases, cases)]
    metrics = llm_eval.aggregate(ecases, results)
    thresholds = []
    passed = True
    if s.linked_model is not None:
        for t in s.linked_model.thresholds:
            if t.metric in metrics and t.is_active:
                status = evaluate(metrics[t.metric], t.direction, t.warning_limit, t.breach_limit)
                thresholds.append({"metric": t.metric, "value": metrics[t.metric], "warning_limit": t.warning_limit,
                                   "breach_limit": t.breach_limit, "direction": t.direction, "status": status})
                passed &= status != "Breach"
    n = db.execute(select(func.count()).select_from(LLMEvalRun)).scalar()
    run = LLMEvalRun(run_id=f"EVAL-{n + 1:04d}", ai_system_id=s.id, model_version=model_version,
                     case_count=len(cases), metrics=metrics, threshold_results=thresholds, passed=passed,
                     triggered_by=actor[0], run_at=run_at or datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    for c, r in zip(cases, results):
        db.add(LLMEvalResult(run_id=run.id, case_id=c.id, response_text=recorded[c.id].response_text,
                             facts_expected=r.facts_expected, facts_found=r.facts_found, claims_total=r.claims_total,
                             unsupported_claims=r.unsupported_claims, hallucinated_references=r.hallucinated_references,
                             policy_violations=r.policy_violations, behavior_correct=r.behavior_correct,
                             normalized_answer=r.normalized_answer, reviewer_decision=r.reviewer_decision,
                             passed=r.passed))
    s.hallucination_evaluation = (f"{run.run_id} on {model_version}: hallucination "
                                  f"{_pct(metrics['hallucination_rate'])}, factual accuracy "
                                  f"{_pct(metrics['factual_accuracy'])}, policy compliance "
                                  f"{_pct(metrics['policy_compliance'])}; {'passed' if passed else 'breached'} thresholds.")
    audit.record(db, actor[0], actor[1], "LLM_EVALUATION_RUN", "ai_system", s.system_id,
                 f"{run.run_id} {model_version}: {'passed' if passed else 'threshold breach'}",
                 {"metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in metrics.items()},
                  "breaches": [t["metric"] for t in thresholds if t["status"] == "Breach"]})
    return run


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


# ---------------------------------------------------------------------------------------------
# Bias testing
# ---------------------------------------------------------------------------------------------

BIAS_SOURCES = {"MDL-COR-010": "applications", "MDL-SAD-007": "transactions"}


def run_bias_test(db: Session, actor: tuple, s: AISystem, periods: int = 3) -> BiasTestResult:
    model = s.linked_model
    if model is None or model.model_id not in BIAS_SOURCES:
        raise WorkflowError("Outcome disparity testing is available for systems linked to MDL-COR-010 or MDL-SAD-007")
    ps = list(db.execute(select(SimulationPeriod.period).order_by(SimulationPeriod.period.desc()).limit(periods))
              .scalars())
    if BIAS_SOURCES[model.model_id] == "applications":
        rows = db.execute(select(ScoredRecord.predicted, ScoredRecord.actual, Application.nationality_region)
                          .join(Application, Application.application_id == ScoredRecord.record_ref)
                          .where(ScoredRecord.model_id == model.id, ScoredRecord.period.in_(ps))).all()
        adverse = "Referred to enhanced due diligence"
    else:
        rows = db.execute(select(ScoredRecord.predicted, ScoredRecord.actual, Customer.nationality_region)
                          .join(Transaction, Transaction.txn_id == ScoredRecord.record_ref)
                          .join(Customer, Customer.customer_id == Transaction.customer_id)
                          .where(ScoredRecord.model_id == model.id, ScoredRecord.period.in_(ps))).all()
        adverse = "Transaction alerted"
    df = pd.DataFrame(rows, columns=["predicted", "actual", "group"])
    res = bias_an.disparity(df, "group", "predicted", "actual")
    out = BiasTestResult(ai_system_id=s.id, attribute="Nationality region (synthetic)",
                         reference_group=res["reference_group"] or "", groups=res["groups"],
                         min_ratio=res["min_impact_ratio"], min_fpr_ratio=res["min_fpr_ratio"],
                         passed=bool(res["passed"]), records=len(df),
                         method=(f"Adverse outcome: {adverse}. Impact ratio of favourable-outcome rates and ratio of "
                                 f"false positive rates against the best group; flag below 0.80."),
                         periods=f"{min(ps)} to {max(ps)}", run_by=actor[0])
    db.add(out)
    s.bias_testing_status = "Passed" if out.passed else "Review required"
    s.bias_testing_summary = (f"{out.periods}, {len(df):,} records: minimum impact ratio "
                              f"{out.min_ratio:.3f}, minimum FPR ratio "
                              f"{(out.min_fpr_ratio or 0):.3f} across nationality regions.")
    db.flush()
    audit.record(db, actor[0], actor[1], "BIAS_TEST_RUN", "ai_system", s.system_id,
                 f"Outcome disparity test {'passed' if out.passed else 'flagged groups for review'}",
                 {"min_impact_ratio": out.min_ratio, "min_fpr_ratio": out.min_fpr_ratio, "periods": out.periods})
    return out


def linked_model_by_id(db: Session, model_id: Optional[str]) -> Optional[int]:
    if not model_id:
        return None
    m = db.execute(select(InventoryModel.id).where(InventoryModel.model_id == model_id)).scalar()
    if m is None:
        raise NotFound(f"Model {model_id} not found")
    return m
