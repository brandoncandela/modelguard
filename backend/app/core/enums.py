"""Controlled vocabularies shared by the database, API and services."""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value

    @classmethod
    def values(cls):
        return [m.value for m in cls]


class Role(StrEnum):
    ADMIN = "admin"
    MODEL_OWNER = "model_owner"
    VALIDATOR = "validator"
    COMPLIANCE_REVIEWER = "compliance_reviewer"


class ModelCategory(StrEnum):
    TRANSACTION_MONITORING = "Transaction Monitoring"
    SANCTIONS_FILTERING = "Sanctions Filtering"
    NAME_SCREENING = "Name Screening"
    CUSTOMER_RISK_RATING = "Customer Risk Rating"
    PEP_SCREENING = "PEP Screening"
    ADVERSE_MEDIA = "Adverse Media Screening"
    ANOMALY_DETECTION = "Suspicious Activity Detection"
    AI_INVESTIGATIONS = "AI-Assisted Investigations"
    LLM_RESEARCH = "LLM Compliance Research"
    ONBOARDING_RISK = "Onboarding Risk Classification"


class MethodologyType(StrEnum):
    RULES = "Rules-based"
    STATISTICAL = "Statistical scoring"
    MACHINE_LEARNING = "Machine learning"
    FUZZY_MATCHING = "Fuzzy name matching"
    NLP = "NLP classification"
    LLM = "Large language model"


class RiskRating(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# Months between full validations by risk rating (internal policy MRM-POL-001)
VALIDATION_CYCLE_MONTHS = {RiskRating.HIGH.value: 12, RiskRating.MEDIUM.value: 24, RiskRating.LOW.value: 36}


class SupervisoryClass(StrEnum):
    """Whether the April 2026 interagency guidance (SR 26-2 / OCC Bulletin 2026-13) treats an entry as a model."""

    MODEL = "Model under SR 26-2"
    DETERMINISTIC = "Outside SR 26-2 definition (deterministic)"
    GENERATIVE = "Outside SR 26-2 scope (generative AI)"


class LifecycleStage(StrEnum):
    DEVELOPMENT = "Development"
    PRE_IMPLEMENTATION = "Pre-Implementation Validation"
    PRODUCTION = "Production"
    UNDER_REMEDIATION = "Under Remediation"
    RETIRED = "Retired"


class ApprovalStatus(StrEnum):
    APPROVED = "Approved"
    CONDITIONALLY_APPROVED = "Conditionally Approved"
    PENDING = "Pending Approval"
    NOT_APPROVED = "Not Approved"
    EXPIRED = "Approval Expired"


class DocumentationStatus(StrEnum):
    COMPLETE = "Complete"
    PARTIAL = "Partial"
    INCOMPLETE = "Incomplete"
    OUTDATED = "Outdated"


DOCUMENTATION_ARTIFACTS = [
    "Model development document",
    "Methodology and assumptions",
    "Data lineage and sources",
    "Ongoing monitoring plan",
    "User procedures",
    "Limitations and compensating controls",
]


class MonitoringFrequency(StrEnum):
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"


class Metric(StrEnum):
    PRECISION = "precision"
    RECALL = "recall"
    F1 = "f1"
    FALSE_POSITIVE_RATE = "false_positive_rate"
    ALERT_CONVERSION_RATE = "alert_conversion_rate"
    ALERT_RATE = "alert_rate"
    PSI = "psi"
    DQ_EXCEPTION_RATE = "dq_exception_rate"
    MAX_FEATURE_PSI = "max_feature_psi"
    OVERRIDE_RATE = "override_rate"
    # LLM evaluation metrics (Module D) can also carry thresholds
    FACTUAL_ACCURACY = "factual_accuracy"
    HALLUCINATION_RATE = "hallucination_rate"
    UNSUPPORTED_CLAIM_RATE = "unsupported_claim_rate"
    POLICY_COMPLIANCE = "policy_compliance"
    RESPONSE_CONSISTENCY = "response_consistency"


class ThresholdDirection(StrEnum):
    MIN = "min"  # value below the limit is adverse (e.g. recall)
    MAX = "max"  # value above the limit is adverse (e.g. PSI)


class MetricStatus(StrEnum):
    OK = "Within limits"
    WARNING = "Warning"
    BREACH = "Breach"
    NOT_AVAILABLE = "Not available"


class Severity(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


SEVERITY_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


class BreachStatus(StrEnum):
    OPEN = "Open"
    ACKNOWLEDGED = "Acknowledged"
    RESOLVED = "Resolved"


class ValidationStatus(StrEnum):
    NOT_STARTED = "Not Started"
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    PENDING_REVIEW = "Pending Review"
    APPROVED = "Approved"
    CONDITIONALLY_APPROVED = "Conditionally Approved"
    REJECTED = "Rejected"


class ValidationType(StrEnum):
    INITIAL = "Initial"
    PERIODIC = "Periodic"
    CHANGE = "Change / Targeted"


VALIDATION_SCOPE_AREAS = [
    "Conceptual soundness",
    "Data integrity and lineage",
    "Implementation and process verification",
    "Outcomes analysis and back-testing",
    "Benchmarking",
    "Ongoing monitoring review",
    "Threshold and tuning review",
    "Documentation review",
]


class FindingStatus(StrEnum):
    OPEN = "Open"
    RESPONSE_SUBMITTED = "Response Submitted"
    IN_REMEDIATION = "In Remediation"
    PENDING_VALIDATION = "Pending Validation"
    CLOSED = "Closed"
    RISK_ACCEPTED = "Risk Accepted"


FINDING_OPEN_STATUSES = [
    FindingStatus.OPEN.value,
    FindingStatus.RESPONSE_SUBMITTED.value,
    FindingStatus.IN_REMEDIATION.value,
    FindingStatus.PENDING_VALIDATION.value,
]


class FindingCategory(StrEnum):
    CONCEPTUAL = "Conceptual soundness"
    DATA = "Data quality"
    IMPLEMENTATION = "Implementation"
    PERFORMANCE = "Performance"
    DOCUMENTATION = "Documentation"
    GOVERNANCE = "Governance"


class AIApprovalStatus(StrEnum):
    DRAFT = "Draft"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    APPROVED_WITH_CONDITIONS = "Approved with Conditions"
    REJECTED = "Rejected"
    RETIRED = "Retired"


class EUAIActClass(StrEnum):
    PROHIBITED = "Prohibited practice (Art. 5)"
    HIGH_RISK = "High-risk (Art. 6, Annex III)"
    TRANSPARENCY = "Transparency obligations (Art. 50)"
    MINIMAL = "Minimal risk"
    NOT_ASSESSED = "Not assessed"


class AssessmentStatus(StrEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    RETURNED = "Returned"


class Answer(StrEnum):
    YES = "Yes"
    PARTIAL = "Partial"
    NO = "No"
    NA = "N/A"


class SourceType(StrEnum):
    REGULATION = "Regulation"
    SUPERVISORY_GUIDANCE = "Supervisory guidance"
    INTERNAL_POLICY = "Internal policy"


class ControlStatus(StrEnum):
    IMPLEMENTED = "Implemented"
    PARTIAL = "Partially implemented"
    NOT_IMPLEMENTED = "Not implemented"
    PLANNED = "Planned"
