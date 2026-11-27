"""Model inventory rules (Module A)."""
from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from app.core.enums import DOCUMENTATION_ARTIFACTS, DocumentationStatus

DOC_STALE_DAYS = 730  # documentation older than 24 months is Outdated (MRM-POL-001)


def documentation_completeness(checklist: Dict[str, bool]) -> float:
    present = sum(1 for a in DOCUMENTATION_ARTIFACTS if checklist.get(a))
    return present / len(DOCUMENTATION_ARTIFACTS)


def derive_documentation_status(checklist: Dict[str, bool], reviewed_on: Optional[date], today: date) -> str:
    if reviewed_on is not None and (today - reviewed_on).days > DOC_STALE_DAYS:
        return DocumentationStatus.OUTDATED.value
    c = documentation_completeness(checklist)
    if c >= 1.0:
        return DocumentationStatus.COMPLETE.value
    if c >= 0.5:
        return DocumentationStatus.PARTIAL.value
    return DocumentationStatus.INCOMPLETE.value


# ---------------------------------------------------------------------------------------------
# CRUD and queries
# ---------------------------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402
from typing import Any, List, Tuple  # noqa: E402

from sqlalchemy import case, func, or_, select  # noqa: E402
from sqlalchemy.orm import Session, aliased  # noqa: E402

from app.core.enums import (  # noqa: E402
    FINDING_OPEN_STATUSES,
    VALIDATION_CYCLE_MONTHS,
    ApprovalStatus,
    BreachStatus,
)
from app.core.errors import Forbidden, NotFound, WorkflowError, Conflict  # noqa: E402
from app.models.inventory import InventoryModel  # noqa: E402
from app.models.monitoring import Breach, MonitoringRun  # noqa: E402
from app.models.users import User  # noqa: E402
from app.models.validation import Finding, Validation  # noqa: E402
from app.services import audit  # noqa: E402

DUE_SOON_DAYS = 90
EDITABLE_FIELDS = [
    "name", "description", "business_owner_id", "model_risk_owner_id", "business_unit", "category", "methodology",
    "methodology_type", "vendor", "version", "developer", "geographies", "risk_rating", "risk_rationale",
    "supervisory_classification", "classification_rationale", "lifecycle_stage", "implementation_date", "last_validation_date", "next_validation_date", "approval_status",
    "documentation_checklist", "documentation_reviewed_on", "limitations", "monitoring_frequency",
]
RISK_ORDER = case({"High": 3, "Medium": 2, "Low": 1}, value=InventoryModel.risk_rating, else_=0)
SORTABLE = {
    "model_id": InventoryModel.model_id, "name": InventoryModel.name, "risk_rating": RISK_ORDER,
    "next_validation_date": InventoryModel.next_validation_date, "lifecycle_stage": InventoryModel.lifecycle_stage,
    "approval_status": InventoryModel.approval_status, "business_unit": InventoryModel.business_unit,
    "updated_at": InventoryModel.updated_at, "category": InventoryModel.category,
}


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    import calendar

    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def validation_state(model: InventoryModel, today: date) -> Tuple[str, Optional[int]]:
    if model.next_validation_date is None:
        return ("Not yet validated" if model.last_validation_date is None else "No date set"), None
    days = (model.next_validation_date - today).days
    if days < 0:
        return "Overdue", days
    if days <= DUE_SOON_DAYS:
        return "Due within 90 days", days
    return "Current", days


def snapshot(model: InventoryModel) -> Dict[str, Any]:
    return {f: getattr(model, f) for f in EDITABLE_FIELDS + ["documentation_status", "is_archived"]}


def can_edit(user: User, model: InventoryModel) -> bool:
    if user.role == "admin":
        return True
    return user.role == "model_owner" and user.id in (model.business_owner_id, model.model_risk_owner_id)


def get_model(db: Session, model_id: str) -> InventoryModel:
    m = db.execute(select(InventoryModel).where(InventoryModel.model_id == model_id)).unique().scalar_one_or_none()
    if m is None:
        raise NotFound(f"Model {model_id} not found")
    return m


def _counts(db: Session, ids: List[int]) -> Tuple[Dict[int, int], Dict[int, int], Dict[int, str]]:
    if not ids:
        return {}, {}, {}
    f = dict(db.execute(select(Finding.model_id, func.count()).where(
        Finding.model_id.in_(ids), Finding.status.in_(FINDING_OPEN_STATUSES)).group_by(Finding.model_id)).all())
    b = dict(db.execute(select(Breach.model_id, func.count()).where(
        Breach.model_id.in_(ids), Breach.status != BreachStatus.RESOLVED.value, Breach.level == "Breach"
    ).group_by(Breach.model_id)).all())
    s = dict(db.execute(select(MonitoringRun.model_id, MonitoringRun.overall_status).where(
        MonitoringRun.model_id.in_(ids), MonitoringRun.is_latest.is_(True))
        .order_by(MonitoringRun.period)).all())
    return f, b, s


def to_out(db: Session, models: List[InventoryModel], today: date, user: Optional[User] = None) -> List[Dict[str, Any]]:
    f, b, s = _counts(db, [m.id for m in models])
    out = []
    for m in models:
        state, days = validation_state(m, today)
        d = {c: getattr(m, c) for c in (
            "id", "model_id", "name", "description", "business_owner", "model_risk_owner", "developer",
            "business_unit", "category", "methodology", "methodology_type", "vendor", "version", "geographies",
            "risk_rating", "risk_rationale", "supervisory_classification", "classification_rationale",
            "lifecycle_stage", "implementation_date", "last_validation_date",
            "next_validation_date", "approval_status", "documentation_checklist", "documentation_reviewed_on",
            "documentation_status", "limitations", "monitoring_frequency", "is_archived", "archived_at",
            "archived_reason", "created_at", "updated_at")}
        d.update(documentation_completeness=round(documentation_completeness(m.documentation_checklist or {}) * 100, 1),
                 validation_state=state, days_to_next_validation=days, open_findings=f.get(m.id, 0),
                 open_breaches=b.get(m.id, 0), monitoring_status=s.get(m.id))
        if user is not None:
            d["can_edit"] = can_edit(user, m)
            d["thresholds"] = list(m.thresholds)
        out.append(d)
    return out


def list_models(db: Session, *, q: Optional[str] = None, category: Optional[List[str]] = None,
                risk_rating: Optional[List[str]] = None, lifecycle_stage: Optional[List[str]] = None,
                approval_status: Optional[List[str]] = None, business_unit: Optional[List[str]] = None,
                documentation_status: Optional[List[str]] = None, validation_due: Optional[str] = None,
                include_archived: bool = False, archived_only: bool = False, sort: str = "model_id",
                direction: str = "asc", page: int = 1, page_size: int = 50, today: Optional[date] = None
                ) -> Tuple[List[InventoryModel], int]:
    stmt = select(InventoryModel)
    bo = aliased(User)
    ro = aliased(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.join(bo, InventoryModel.business_owner_id == bo.id).join(ro, InventoryModel.model_risk_owner_id == ro.id)
        stmt = stmt.where(or_(InventoryModel.model_id.ilike(like), InventoryModel.name.ilike(like),
                              InventoryModel.description.ilike(like), InventoryModel.methodology.ilike(like),
                              InventoryModel.limitations.ilike(like), InventoryModel.business_unit.ilike(like),
                              InventoryModel.category.ilike(like), bo.full_name.ilike(like), ro.full_name.ilike(like)))
    for col, vals in ((InventoryModel.category, category), (InventoryModel.risk_rating, risk_rating),
                      (InventoryModel.lifecycle_stage, lifecycle_stage), (InventoryModel.approval_status, approval_status),
                      (InventoryModel.business_unit, business_unit),
                      (InventoryModel.documentation_status, documentation_status)):
        if vals:
            stmt = stmt.where(col.in_(vals))
    if archived_only:
        stmt = stmt.where(InventoryModel.is_archived.is_(True))
    elif not include_archived:
        stmt = stmt.where(InventoryModel.is_archived.is_(False))
    if validation_due and today:
        if validation_due == "overdue":
            stmt = stmt.where(InventoryModel.next_validation_date < today)
        elif validation_due == "due_90d":
            stmt = stmt.where(InventoryModel.next_validation_date >= today,
                              InventoryModel.next_validation_date <= today + timedelta(days=DUE_SOON_DAYS))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    col = SORTABLE.get(sort, InventoryModel.model_id)
    order = col.desc() if direction == "desc" else col.asc()
    stmt = stmt.order_by(order, InventoryModel.model_id).offset((page - 1) * page_size).limit(page_size)
    return list(db.execute(stmt).unique().scalars()), total


def _check_owner(db: Session, user_id: int, field: str) -> None:
    u = db.get(User, user_id)
    if u is None or not u.is_active:
        raise WorkflowError(f"{field}: user {user_id} not found or inactive")
    if u.role not in ("model_owner", "admin"):
        raise WorkflowError(f"{field}: {u.full_name} has role '{u.role}'; owners must be model owners")


def create_model(db: Session, user: User, data: Dict[str, Any], today: date) -> InventoryModel:
    if db.execute(select(InventoryModel.id).where(InventoryModel.model_id == data["model_id"])).first():
        raise Conflict(f"Model ID {data['model_id']} already exists")
    _check_owner(db, data["business_owner_id"], "business_owner_id")
    _check_owner(db, data["model_risk_owner_id"], "model_risk_owner_id")
    if user.role == "model_owner" and user.id not in (data["business_owner_id"], data["model_risk_owner_id"]):
        raise Forbidden("Model owners can only register models they own")
    if user.role != "admin" and data.get("approval_status") not in (None, ApprovalStatus.PENDING.value):
        raise Forbidden("New models start as Pending Approval; approval comes from validation")
    m = InventoryModel(**data)
    if m.last_validation_date and not m.next_validation_date:
        m.next_validation_date = add_months(m.last_validation_date, VALIDATION_CYCLE_MONTHS[m.risk_rating])
    m.documentation_status = derive_documentation_status(m.documentation_checklist or {}, m.documentation_reviewed_on, today)
    db.add(m)
    db.flush()
    audit.record(db, user.username, user.role, "MODEL_CREATED", "model", m.model_id, f"Registered {m.name}",
                 {k: v for k, v in snapshot(m).items() if v not in (None, "", [], {})})
    return m


def update_model(db: Session, user: User, m: InventoryModel, changes: Dict[str, Any], today: date) -> InventoryModel:
    if m.is_archived:
        raise WorkflowError("Archived models are read-only; restore the model first")
    if not can_edit(user, m):
        raise Forbidden("Only the model's owners or an administrator can edit this model")
    if user.role != "admin":
        for f in ("approval_status", "last_validation_date", "next_validation_date"):
            if f in changes and changes[f] != getattr(m, f):
                raise Forbidden(f"'{f}' is set by the validation workflow or an administrator")
    for f in ("business_owner_id", "model_risk_owner_id"):
        if f in changes and changes[f] is not None:
            _check_owner(db, changes[f], f)
    before = snapshot(m)
    for k, v in changes.items():
        if k in EDITABLE_FIELDS:
            setattr(m, k, v)
    if "risk_rating" in changes and m.last_validation_date and "next_validation_date" not in changes:
        m.next_validation_date = add_months(m.last_validation_date, VALIDATION_CYCLE_MONTHS[m.risk_rating])
    if m.last_validation_date and m.next_validation_date and m.next_validation_date <= m.last_validation_date:
        raise WorkflowError("next_validation_date must be after last_validation_date")
    m.documentation_status = derive_documentation_status(m.documentation_checklist or {}, m.documentation_reviewed_on, today)
    m.updated_at = datetime.now(timezone.utc)
    delta = audit.diff(before, snapshot(m))
    if not delta:
        return m
    action = "MODEL_RISK_RERATED" if "risk_rating" in delta else "MODEL_UPDATED"
    audit.record(db, user.username, user.role, action, "model", m.model_id,
                 f"Updated {', '.join(sorted(delta))}", delta)
    return m


def archive_model(db: Session, user: User, m: InventoryModel, reason: str) -> InventoryModel:
    if m.is_archived:
        raise WorkflowError("Model is already archived")
    active = db.execute(select(Validation.validation_id).where(
        Validation.model_id == m.id, Validation.status.in_(["In Progress", "Pending Review"]))).scalars().all()
    if active:
        raise WorkflowError(f"Cannot archive while validation {', '.join(active)} is in progress")
    m.is_archived = True
    m.archived_at = datetime.now(timezone.utc)
    m.archived_reason = reason
    audit.record(db, user.username, user.role, "MODEL_ARCHIVED", "model", m.model_id, f"Archived: {reason}",
                 {"is_archived": {"from": False, "to": True}, "reason": reason})
    return m


def restore_model(db: Session, user: User, m: InventoryModel) -> InventoryModel:
    if not m.is_archived:
        raise WorkflowError("Model is not archived")
    m.is_archived = False
    m.archived_at = None
    m.archived_reason = None
    audit.record(db, user.username, user.role, "MODEL_RESTORED", "model", m.model_id, "Restored to active inventory",
                 {"is_archived": {"from": True, "to": False}})
    return m
