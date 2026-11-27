from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.config import get_settings
from app.core.enums import (
    FINDING_OPEN_STATUSES,
    VALIDATION_SCOPE_AREAS,
    FindingCategory,
    FindingStatus,
    Severity,
    ValidationStatus,
    ValidationType,
)
from app.core.errors import Forbidden, NotFound
from app.core.permissions import has_permission
from app.db.session import get_db
from app.models.inventory import InventoryModel
from app.models.users import User
from app.models.validation import Evidence, Finding, Validation, WorkflowEvent
from app.services import validation as svc

router = APIRouter()


def user_ref(u: Optional[User]):
    return None if u is None else {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
                                   "title": u.title}


def evidence_out(e: Evidence):
    return {"evidence_id": e.evidence_id, "title": e.title, "evidence_type": e.evidence_type,
            "description": e.description, "file_name": e.file_name, "content_type": e.content_type,
            "file_size": e.file_size, "sha256": e.sha256, "uploaded_by": user_ref(e.uploaded_by),
            "uploaded_at": e.uploaded_at, "has_file": bool(e.storage_key)}


def events_out(db: Session, entity_type: str, entity_id: int):
    rows = db.execute(select(WorkflowEvent).where(WorkflowEvent.entity_type == entity_type,
                                                  WorkflowEvent.entity_id == entity_id)
                      .order_by(WorkflowEvent.occurred_at, WorkflowEvent.id)).scalars()
    return [{"event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status,
             "actor": user_ref(e.actor), "comment": e.comment, "data": e.data, "occurred_at": e.occurred_at}
            for e in rows]


def evidence_for(db: Session, entity_type: str, entity_id: int):
    return [evidence_out(e) for e in db.execute(select(Evidence).where(
        Evidence.entity_type == entity_type, Evidence.entity_id == entity_id).order_by(Evidence.uploaded_at)).scalars()]


def validation_actions(user: User, v: Validation) -> List[str]:
    out = []
    for to in svc.VALIDATION_TRANSITIONS.get(v.status, []):
        if v.status in ("Not Started", "Scheduled") and to in ("Scheduled", "Not Started"):
            ok = user.role in ("admin", "compliance_reviewer")
        elif v.status == "Scheduled" and to == "In Progress":
            ok = user.id == v.lead_validator_id
        elif to == "Pending Review":
            ok = user.id == v.lead_validator_id
        elif v.status == "Pending Review":
            ok = user.role in ("admin", "compliance_reviewer") and user.id not in svc.team_ids(v) \
                and not svc.is_owner(user, v.model)
        else:
            ok = False
        if ok:
            out.append(to)
    return out


def finding_summary_line(f: Finding, today: date):
    overdue = svc.finding_overdue(f, today)
    return {"finding_id": f.finding_id, "title": f.title, "severity": f.severity, "status": f.status,
            "category": f.category, "target_date": f.target_date, "overdue": overdue,
            "days_overdue": (today - f.target_date).days if overdue else 0}


def validation_out(db: Session, v: Validation, user: User, full: bool = False):
    today = get_settings().today()
    team = [db.get(User, int(i)) for i in (v.team or [])]
    findings = list(v.findings)
    d = {
        "validation_id": v.validation_id, "status": v.status, "validation_type": v.validation_type,
        "model": {"model_id": v.model.model_id, "name": v.model.name, "risk_rating": v.model.risk_rating,
                  "category": v.model.category},
        "scope_areas": v.scope_areas, "scope_notes": v.scope_notes, "lead_validator": user_ref(v.lead_validator),
        "team": [user_ref(u) for u in team if u], "independence_attested": v.independence_attested,
        "independence_statement": v.independence_statement, "scheduled_start": v.scheduled_start,
        "scheduled_end": v.scheduled_end, "actual_start": v.actual_start, "submitted_on": v.submitted_on,
        "decided_on": v.decided_on, "overall_rating": v.overall_rating, "summary": v.summary,
        "conditions": v.conditions,
        "schedule_overdue": bool(v.status in svc.ACTIVE_VALIDATION and v.scheduled_end and v.scheduled_end < today),
        "findings_total": len(findings),
        "findings_open": sum(1 for f in findings if f.status in FINDING_OPEN_STATUSES),
        "findings_by_severity": {s: sum(1 for f in findings if f.severity == s) for s in Severity.values()},
        "actions": validation_actions(user, v),
    }
    if full:
        d["findings"] = [finding_summary_line(f, today) for f in findings]
        d["evidence"] = evidence_for(db, "validation", v.id)
        d["approvals"] = [{"approver": user_ref(a.approver), "decision": a.decision, "comments": a.comments,
                           "conditions": a.conditions, "decided_at": a.decided_at} for a in v.approvals]
        d["history"] = events_out(db, "validation", v.id)
        d["can_add_evidence"] = v.status in ("In Progress", "Pending Review") and (
            user.id in svc.team_ids(v) or user.role == "admin")
        d["can_raise_findings"] = v.status in ("In Progress", "Pending Review") and user.id in svc.team_ids(v)
    return d


@router.get("/validations/meta", tags=["validations"])
def meta(_: User = Depends(current_user)):
    return {"statuses": ValidationStatus.values(), "types": ValidationType.values(),
            "scope_areas": VALIDATION_SCOPE_AREAS, "ratings": svc.RATINGS, "transitions": svc.VALIDATION_TRANSITIONS,
            "finding_statuses": FindingStatus.values(), "finding_transitions": svc.FINDING_TRANSITIONS,
            "severities": Severity.values(), "categories": FindingCategory.values(),
            "target_days_by_severity": svc.TARGET_DAYS, "evidence_types": sorted(svc.ALLOWED_TYPES)}


@router.get("/validations", tags=["validations"])
def list_validations(status: Optional[List[str]] = Query(None), model_id: Optional[str] = Query(None, max_length=32),
                     lead: Optional[str] = Query(None, max_length=64), db: Session = Depends(get_db),
                     user: User = Depends(require("validation:read"))):
    stmt = select(Validation).join(InventoryModel, Validation.model_id == InventoryModel.id)
    if status:
        stmt = stmt.where(Validation.status.in_(status))
    if model_id:
        stmt = stmt.where(InventoryModel.model_id == model_id)
    if lead:
        stmt = stmt.join(User, Validation.lead_validator_id == User.id).where(User.username == lead)
    vs = db.execute(stmt.order_by(Validation.validation_id.desc())).unique().scalars()
    return [validation_out(db, v, user) for v in vs]


class ValidationCreate(BaseModel):
    model_id: str = Field(pattern=r"^MDL-[A-Z]{2,4}-\d{3}$")
    validation_type: str
    scope_areas: List[str] = Field(default_factory=list, max_length=len(VALIDATION_SCOPE_AREAS))
    scope_notes: str = Field("", max_length=4000)
    lead_validator_id: Optional[int] = None
    team: List[int] = Field(default_factory=list, max_length=6)
    scheduled_start: Optional[date] = None
    scheduled_end: Optional[date] = None


@router.post("/validations", tags=["validations"], status_code=201)
def create_validation(body: ValidationCreate, db: Session = Depends(get_db),
                      user: User = Depends(require("validation:schedule"))):
    v = svc.create_validation(db, user, body.model_dump(), get_settings().today())
    db.commit()
    return validation_out(db, svc.get_validation(db, v.validation_id), user, full=True)


@router.get("/validations/{validation_id}", tags=["validations"])
def get_validation(validation_id: str, db: Session = Depends(get_db), user: User = Depends(require("validation:read"))):
    return validation_out(db, svc.get_validation(db, validation_id), user, full=True)


class ValidationPatch(BaseModel):
    validation_type: Optional[str] = None
    scope_areas: Optional[List[str]] = None
    scope_notes: Optional[str] = Field(None, max_length=4000)
    lead_validator_id: Optional[int] = None
    team: Optional[List[int]] = Field(None, max_length=6)
    scheduled_start: Optional[date] = None
    scheduled_end: Optional[date] = None
    overall_rating: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=8000)
    independence_attested: Optional[bool] = None
    independence_statement: Optional[str] = Field(None, max_length=2000)


@router.patch("/validations/{validation_id}", tags=["validations"])
def patch_validation(validation_id: str, body: ValidationPatch, db: Session = Depends(get_db),
                     user: User = Depends(require("validation:read"))):
    v = svc.get_validation(db, validation_id)
    svc.update_validation(db, user, v, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(v)
    return validation_out(db, v, user, full=True)


class TransitionIn(BaseModel):
    to_status: str
    comment: str = Field("", max_length=4000)
    conditions: str = Field("", max_length=4000)


@router.post("/validations/{validation_id}/transition", tags=["validations"])
def transition(validation_id: str, body: TransitionIn, db: Session = Depends(get_db),
               user: User = Depends(require("validation:read"))):
    v = svc.get_validation(db, validation_id)
    svc.transition_validation(db, user, v, body.to_status, body.comment, body.conditions)
    db.commit()
    db.refresh(v)
    return validation_out(db, v, user, full=True)


async def _read_upload(file: Optional[UploadFile]):
    if file is None or not file.filename:
        return None, None, None
    content = await file.read(svc.MAX_EVIDENCE_BYTES + 1)
    return file.filename, file.content_type, content


@router.post("/validations/{validation_id}/evidence", tags=["validations"], status_code=201)
async def add_validation_evidence(validation_id: str, title: str = Form(..., min_length=3, max_length=200),
                                  evidence_type: str = Form(..., min_length=3, max_length=48),
                                  description: str = Form("", max_length=2000), file: Optional[UploadFile] = File(None),
                                  db: Session = Depends(get_db), user: User = Depends(require("validation:read"))):
    v = svc.get_validation(db, validation_id)
    svc.can_add_validation_evidence(user, v)
    name, ctype, content = await _read_upload(file)
    ev = svc.store_evidence(db, user, "validation", v.id, v.validation_id, title, evidence_type, description,
                            name, ctype, content)
    db.commit()
    return evidence_out(ev)


class FindingCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=6000)
    category: str
    severity: str
    remediation_owner_id: Optional[int] = None
    target_date: Optional[date] = None


@router.post("/validations/{validation_id}/findings", tags=["findings"], status_code=201)
def raise_finding(validation_id: str, body: FindingCreate, db: Session = Depends(get_db),
                  user: User = Depends(require("finding:create"))):
    v = svc.get_validation(db, validation_id)
    f = svc.create_finding(db, user, v, body.model_dump(), get_settings().today())
    db.commit()
    from app.api.routes.findings import finding_out

    return finding_out(db, f, user, full=True)


@router.get("/evidence/{evidence_id}/download", tags=["validations"])
def download_evidence(evidence_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ev = db.execute(select(Evidence).where(Evidence.evidence_id == evidence_id)).scalar_one_or_none()
    if ev is None:
        raise NotFound("Evidence not found")
    perm = {"validation": "validation:read", "finding": "finding:read", "control": "regulatory:read"}.get(
        ev.entity_type, "audit:read")
    if not has_permission(user.role, perm):
        raise Forbidden("Not permitted to download this evidence")
    path = svc.evidence_path(ev)
    return FileResponse(path, media_type=ev.content_type or "application/octet-stream", filename=ev.file_name)


def _count(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
