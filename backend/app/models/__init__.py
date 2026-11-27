"""Import every model so Base.metadata is complete (Alembic and create_all rely on this)."""
from app.models.users import User  # noqa: F401
from app.models.inventory import InventoryModel, ModelThreshold  # noqa: F401
from app.models.data import (  # noqa: F401
    Alert,
    Application,
    Customer,
    MediaArticle,
    ScoredRecord,
    SimulationPeriod,
    SystemSetting,
    Transaction,
    WatchlistEntry,
)
from app.models.monitoring import Breach, FeatureDrift, MetricResult, MonitoringRun  # noqa: F401
from app.models.validation import Evidence, Finding, Validation, ValidationApproval, WorkflowEvent  # noqa: F401
from app.models.ai import (  # noqa: F401
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
from app.models.regulatory import (  # noqa: F401
    Control,
    ControlTestResult,
    RegulatoryRequirement,
    RegulatorySource,
    control_models,
    control_requirements,
)
from app.models.audit import AuditEvent  # noqa: F401
from app.models.reports import Report  # noqa: F401
