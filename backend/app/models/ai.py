from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.inventory import InventoryModel
from app.models.users import User


class AISystem(Base):
    __tablename__ = "ai_systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    linked_model_id: Mapped[Optional[int]] = mapped_column(ForeignKey("models.id"), nullable=True)
    use_case: Mapped[str] = mapped_column(Text)
    business_justification: Mapped[str] = mapped_column(Text)
    business_unit: Mapped[str] = mapped_column(String(80))
    model_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    system_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ai_technique: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(80))
    deployment_status: Mapped[str] = mapped_column(String(32))
    data_sources: Mapped[list] = mapped_column(JSON, default=list)
    intended_use: Mapped[str] = mapped_column(Text)
    prohibited_use: Mapped[str] = mapped_column(Text)
    affects_natural_persons: Mapped[bool] = mapped_column(Boolean, default=True)
    interacts_with_public: Mapped[bool] = mapped_column(Boolean, default=False)
    human_oversight: Mapped[str] = mapped_column(String(32))  # Human-in-the-loop etc.
    oversight_description: Mapped[str] = mapped_column(Text, default="")
    explainability_rating: Mapped[str] = mapped_column(String(16))
    explainability_notes: Mapped[str] = mapped_column(Text, default="")
    bias_testing_status: Mapped[str] = mapped_column(String(32), default="Not tested")
    bias_testing_summary: Mapped[str] = mapped_column(Text, default="")
    performance_monitoring: Mapped[str] = mapped_column(Text, default="")
    hallucination_evaluation: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    internal_risk_tier: Mapped[str] = mapped_column(String(10))
    eu_ai_act_class: Mapped[str] = mapped_column(String(48), default="Not assessed")
    approval_status: Mapped[str] = mapped_column(String(32), index=True)
    approved_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    linked_model: Mapped[Optional[InventoryModel]] = relationship(lazy="joined")
    model_owner: Mapped[User] = relationship(foreign_keys=[model_owner_id], lazy="joined")
    system_owner: Mapped[User] = relationship(foreign_keys=[system_owner_id], lazy="joined")


class AssessmentTemplate(Base):
    __tablename__ = "assessment_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(16))
    framework: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    questions: Mapped[list["AssessmentQuestion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="AssessmentQuestion.order"
    )


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("template_id", "code", name="uq_question_template_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("assessment_templates.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(48))
    text: Mapped[str] = mapped_column(Text)
    guidance: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(120), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    # When answered "Yes", this question sets the EU AI Act classification (risk classification category only)
    classification_trigger: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    order: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped[AssessmentTemplate] = relationship(back_populates="questions")


class AIAssessment(Base):
    __tablename__ = "ai_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("assessment_templates.id"))
    status: Mapped[str] = mapped_column(String(16), index=True)
    assessor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    derived_classification: Mapped[str] = mapped_column(String(48), default="Not assessed")
    category_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    review_comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    ai_system: Mapped[AISystem] = relationship(lazy="joined")
    template: Mapped[AssessmentTemplate] = relationship()
    assessor: Mapped[User] = relationship(foreign_keys=[assessor_id], lazy="joined")
    reviewer: Mapped[Optional[User]] = relationship(foreign_keys=[reviewer_id], lazy="joined")
    responses: Mapped[list["AssessmentResponse"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class AssessmentResponse(Base):
    __tablename__ = "assessment_responses"
    __table_args__ = (UniqueConstraint("assessment_id", "question_id", name="uq_response_question"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("ai_assessments.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(ForeignKey("assessment_questions.id"))
    answer: Mapped[str] = mapped_column(String(8))
    evidence_note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    assessment: Mapped[AIAssessment] = relationship(back_populates="responses")
    question: Mapped[AssessmentQuestion] = relationship(lazy="joined")


class LLMEvalCase(Base):
    __tablename__ = "llm_eval_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    expected_behavior: Mapped[str] = mapped_column(String(16))  # answer or refuse
    expected_facts: Mapped[list] = mapped_column(JSON, default=list)
    allowed_references: Mapped[list] = mapped_column(JSON, default=list)
    consistency_group: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    expected_answer_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)


class LLMRecordedResponse(Base):
    """Captured model outputs that the deterministic suite scores. No live model calls are made."""

    __tablename__ = "llm_recorded_responses"
    __table_args__ = (UniqueConstraint("case_id", "model_version", name="uq_recorded_case_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("llm_eval_cases.id", ondelete="CASCADE"))
    model_version: Mapped[str] = mapped_column(String(32))
    response_text: Mapped[str] = mapped_column(Text)
    reviewer_decision: Mapped[str] = mapped_column(String(16))  # Accepted, Edited, Overridden
    planted_defects: Mapped[list] = mapped_column(JSON, default=list)  # used only to test the evaluator


class LLMEvalRun(Base):
    __tablename__ = "llm_eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(32))
    case_count: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    threshold_results: Mapped[list] = mapped_column(JSON, default=list)
    passed: Mapped[bool] = mapped_column(Boolean)
    triggered_by: Mapped[str] = mapped_column(String(64))
    run_at: Mapped[datetime] = mapped_column(default=utcnow)

    ai_system: Mapped[AISystem] = relationship(lazy="joined")
    results: Mapped[list["LLMEvalResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class LLMEvalResult(Base):
    __tablename__ = "llm_eval_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("llm_eval_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("llm_eval_cases.id"))
    response_text: Mapped[str] = mapped_column(Text)
    facts_expected: Mapped[int] = mapped_column(Integer)
    facts_found: Mapped[int] = mapped_column(Integer)
    claims_total: Mapped[int] = mapped_column(Integer)
    unsupported_claims: Mapped[list] = mapped_column(JSON, default=list)
    hallucinated_references: Mapped[list] = mapped_column(JSON, default=list)
    policy_violations: Mapped[list] = mapped_column(JSON, default=list)
    behavior_correct: Mapped[bool] = mapped_column(Boolean)
    normalized_answer: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    reviewer_decision: Mapped[str] = mapped_column(String(16))
    passed: Mapped[bool] = mapped_column(Boolean)

    run: Mapped[LLMEvalRun] = relationship(back_populates="results")
    case: Mapped[LLMEvalCase] = relationship(lazy="joined")


class BiasTestResult(Base):
    __tablename__ = "bias_test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(ForeignKey("ai_systems.id"), index=True)
    attribute: Mapped[str] = mapped_column(String(48))
    reference_group: Mapped[str] = mapped_column(String(48))
    groups: Mapped[list] = mapped_column(JSON, default=list)
    min_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_fpr_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean)
    records: Mapped[int] = mapped_column(Integer, default=0)
    method: Mapped[str] = mapped_column(Text)
    periods: Mapped[str] = mapped_column(String(40))
    run_by: Mapped[str] = mapped_column(String(64))
    run_at: Mapped[datetime] = mapped_column(default=utcnow)
