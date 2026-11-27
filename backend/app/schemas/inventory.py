from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import (
    DOCUMENTATION_ARTIFACTS,
    ApprovalStatus,
    LifecycleStage,
    MethodologyType,
    ModelCategory,
    MonitoringFrequency,
    SupervisoryClass,
)
from app.schemas.common import ORM, UserRef

RiskRatingT = Literal["High", "Medium", "Low"]


def _check_enum(value, enum_cls, field):
    if value is not None and value not in enum_cls.values():
        raise ValueError(f"{field} must be one of: {', '.join(enum_cls.values())}")
    return value


class ThresholdOut(ORM):
    metric: str
    kind: str
    direction: str
    warning_limit: float
    breach_limit: float
    rationale: str
    is_active: bool


class ModelBase(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = Field("", max_length=2000)
    business_unit: str = Field(min_length=2, max_length=80)
    category: str
    methodology: str = Field(min_length=10, max_length=4000)
    methodology_type: str
    vendor: str = Field("In-house", max_length=80)
    version: str = Field("1.0", max_length=20, pattern=r"^[0-9A-Za-z.\-]+$")
    developer: str = Field("", max_length=120)
    geographies: List[str] = Field(default_factory=list, max_length=20)
    risk_rating: RiskRatingT
    risk_rationale: str = Field("", max_length=2000)
    supervisory_classification: str = "Model under SR 26-2"
    classification_rationale: str = Field("", max_length=2000)
    lifecycle_stage: str
    implementation_date: Optional[date] = None
    last_validation_date: Optional[date] = None
    next_validation_date: Optional[date] = None
    approval_status: str = ApprovalStatus.PENDING.value
    documentation_checklist: Dict[str, bool] = Field(default_factory=dict)
    documentation_reviewed_on: Optional[date] = None
    limitations: str = Field("", max_length=4000)
    monitoring_frequency: str = MonitoringFrequency.MONTHLY.value

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        return _check_enum(v, ModelCategory, "category")

    @field_validator("methodology_type")
    @classmethod
    def _mt(cls, v):
        return _check_enum(v, MethodologyType, "methodology_type")

    @field_validator("lifecycle_stage")
    @classmethod
    def _ls(cls, v):
        return _check_enum(v, LifecycleStage, "lifecycle_stage")

    @field_validator("approval_status")
    @classmethod
    def _ap(cls, v):
        return _check_enum(v, ApprovalStatus, "approval_status")

    @field_validator("monitoring_frequency")
    @classmethod
    def _mf(cls, v):
        return _check_enum(v, MonitoringFrequency, "monitoring_frequency")

    @field_validator("supervisory_classification")
    @classmethod
    def _sc(cls, v):
        return _check_enum(v, SupervisoryClass, "supervisory_classification")

    @field_validator("documentation_checklist")
    @classmethod
    def _docs(cls, v):
        unknown = set(v) - set(DOCUMENTATION_ARTIFACTS)
        if unknown:
            raise ValueError(f"Unknown documentation artifacts: {sorted(unknown)}")
        return v

    @field_validator("geographies")
    @classmethod
    def _geo(cls, v):
        return [g.strip()[:60] for g in v if g and g.strip()]

    @model_validator(mode="after")
    def _dates(self):
        if self.last_validation_date and self.next_validation_date and \
                self.next_validation_date <= self.last_validation_date:
            raise ValueError("next_validation_date must be after last_validation_date")
        return self


class ModelCreate(ModelBase):
    model_id: str = Field(pattern=r"^MDL-[A-Z]{2,4}-\d{3}$", description="Format MDL-XXX-000")
    business_owner_id: int
    model_risk_owner_id: int


class ModelUpdate(BaseModel):
    """Partial update. Fields left out are unchanged."""

    name: Optional[str] = Field(None, min_length=3, max_length=160)
    description: Optional[str] = Field(None, max_length=2000)
    business_owner_id: Optional[int] = None
    model_risk_owner_id: Optional[int] = None
    business_unit: Optional[str] = Field(None, min_length=2, max_length=80)
    category: Optional[str] = None
    methodology: Optional[str] = Field(None, min_length=10, max_length=4000)
    methodology_type: Optional[str] = None
    vendor: Optional[str] = Field(None, max_length=80)
    version: Optional[str] = Field(None, max_length=20, pattern=r"^[0-9A-Za-z.\-]+$")
    developer: Optional[str] = Field(None, max_length=120)
    geographies: Optional[List[str]] = Field(None, max_length=20)
    risk_rating: Optional[RiskRatingT] = None
    risk_rationale: Optional[str] = Field(None, max_length=2000)
    supervisory_classification: Optional[str] = None
    classification_rationale: Optional[str] = Field(None, max_length=2000)
    lifecycle_stage: Optional[str] = None
    implementation_date: Optional[date] = None
    last_validation_date: Optional[date] = None
    next_validation_date: Optional[date] = None
    approval_status: Optional[str] = None
    documentation_checklist: Optional[Dict[str, bool]] = None
    documentation_reviewed_on: Optional[date] = None
    limitations: Optional[str] = Field(None, max_length=4000)
    monitoring_frequency: Optional[str] = None

    @field_validator("category", "methodology_type", "lifecycle_stage", "approval_status", "monitoring_frequency",
                     "supervisory_classification")
    @classmethod
    def _enums(cls, v, info):
        enum_cls = {"category": ModelCategory, "methodology_type": MethodologyType, "lifecycle_stage": LifecycleStage,
                    "approval_status": ApprovalStatus, "monitoring_frequency": MonitoringFrequency,
                    "supervisory_classification": SupervisoryClass}[info.field_name]
        return _check_enum(v, enum_cls, info.field_name)

    @field_validator("documentation_checklist")
    @classmethod
    def _docs(cls, v):
        if v is not None:
            unknown = set(v) - set(DOCUMENTATION_ARTIFACTS)
            if unknown:
                raise ValueError(f"Unknown documentation artifacts: {sorted(unknown)}")
        return v


class ArchiveRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class ModelOut(ORM):
    id: int
    model_id: str
    name: str
    description: str
    business_owner: UserRef
    model_risk_owner: UserRef
    developer: str
    business_unit: str
    category: str
    methodology: str
    methodology_type: str
    vendor: str
    version: str
    geographies: List[str]
    risk_rating: str
    risk_rationale: str
    supervisory_classification: str
    classification_rationale: str
    lifecycle_stage: str
    implementation_date: Optional[date]
    last_validation_date: Optional[date]
    next_validation_date: Optional[date]
    approval_status: str
    documentation_checklist: Dict[str, bool]
    documentation_reviewed_on: Optional[date]
    documentation_status: str
    limitations: str
    monitoring_frequency: str
    is_archived: bool
    archived_at: Optional[datetime]
    archived_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    # computed
    documentation_completeness: float = 0.0
    validation_state: str = ""
    days_to_next_validation: Optional[int] = None
    open_findings: int = 0
    open_breaches: int = 0
    monitoring_status: Optional[str] = None


class ModelDetail(ModelOut):
    thresholds: List[ThresholdOut] = []
    can_edit: bool = False


class Facets(BaseModel):
    categories: List[str]
    risk_ratings: List[str]
    lifecycle_stages: List[str]
    approval_statuses: List[str]
    documentation_statuses: List[str]
    business_units: List[str]
    methodology_types: List[str]
    monitoring_frequencies: List[str]
    documentation_artifacts: List[str]
    supervisory_classifications: List[str]
