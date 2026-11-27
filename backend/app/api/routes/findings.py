from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.api.routes.validations import _read_upload, events_out, evidence_for, evidence_out, user_ref
from app.core.config import get_settings
from app.core.enums import FINDING_OPEN_STATUSES, Severity
from app.core.errors import Forbidden
from app.db.session import get_db
from app.models.inventory import InventoryModel
from app.models.users import User
from app.models.validation import Finding
from app.services import validation as svc

router = APIRouter(tags=["findings"])


def finding_actions(user: User, f: Finding) -> List[str]:
    owner = svc.is_owner(user, f.model) or user.id == f.remediation_owner_id or user.role == "admin"
    out = []
    if f.status in ("Open", "Response Submitted") and owner and user.role in ("model_owner", "admin"):
        out.append("respond")
    for to in svc.FINDING_TRANSITIONS.get(f.status, []):
        if to == "Response Submitted":
            continue
        if f.status == "Response Submitted" and to in ("In Remediation", "Open"):
            ok = user.role == "validator" and not svc.is_owner(user, f.model)
        elif to == "Pending Validation":
            ok = owner and user.role in ("model_owner", "admin")
        elif f.status == "Pending Validation":
            ok = user.role == "validator" and user.id != f.remediation_owner_id
        elif to == "Risk Accepted":
            ok = user.role in ("admin", "compliance_reviewer") and f.severity != "Critical"
        else:
            ok = False
        if ok:
            out.append(to)
    if f.status in FINDING_OPEN_STATUSES and user.role in ("admin", "compliance_reviewer"):
        out.append("extend")
    if f.status in ("Open", "Response Submitted", "In Remediation") and owner:
        out.append("add_evidence")
    return out


def finding_out(db: Session, f: Finding, user: User, full: bool = False):
    today = get_settings().today()
    overdue = svc.finding_overdue(f, today)
    end = f.closed_on or today
    d = {
        "finding_id": f.finding_id, "validation_id": f.validation.validation_id,
        "model": {"model_id": f.model.model_id, "name": f.model.name, "risk_rating": f.model.risk_rating},
        "title": f.title, "description": f.description, "category": f.category, "severity": f.severity,
        "status": f.status, "raised_by": user_ref(f.raised_by), "raised_on": f.raised_on,
        "management_response": f.management_response, "action_plan": f.action_plan,
        "remediation_owner": user_ref(f.remediation_owner), "target_date": f.target_date,
        "original_target_date": f.original_target_date, "extension_count": f.extension_count,
        "closed_on": f.closed_on, "closed_by": user_ref(f.closed_by),
        "risk_acceptance_rationale": f.risk_acceptance_rationale, "risk_acceptance_expiry": f.risk_acceptance_expiry,
        "overdue": overdue, "days_overdue": (today - f.target_date).days if overdue else 0,
        "age_days": (end - f.raised_on).days, "actions": finding_actions(user, f),
    }
    if full:
        d["evidence"] = evidence_for(db, "finding", f.id)
        d["history"] = events_out(db, "finding", f.id)
    return d


@router.get("/findings")
def list_findings(status: Optional[List[str]] = Query(None), severity: Optional[List[str]] = Query(None),
                  model_id: Optional[str] = Query(None, max_length=32), overdue: Optional[bool] = None,
                  open_only: bool = False, owner: Optional[str] = Query(None, max_length=64),
                  db: Session = Depends(get_db), user: User = Depends(require("finding:read"))):
    today = get_settings().today()
    stmt = select(Finding).join(InventoryModel, Finding.model_id == InventoryModel.id)
    if status:
        stmt = stmt.where(Finding.status.in_(status))
    if open_only:
        stmt = stmt.where(Finding.status.in_(FINDING_OPEN_STATUSES))
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if model_id:
        stmt = stmt.where(InventoryModel.model_id == model_id)
    if owner:
        stmt = stmt.join(User, Finding.remediation_owner_id == User.id).where(User.username == owner)
    if overdue is True:
        stmt = stmt.where(Finding.status.in_(FINDING_OPEN_STATUSES), Finding.target_date < today)
    rows = db.execute(stmt.order_by(Finding.finding_id)).unique().scalars()
    sev_rank = {s: i for i, s in enumerate(Severity.values())}
    items = [finding_out(db, f, user) for f in rows]
    items.sort(key=lambda x: (x["status"] not in FINDING_OPEN_STATUSES, sev_rank.get(x["severity"], 9), x["finding_id"]))
    return items


@router.get("/findings/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(require("finding:read"))):
    today = get_settings().today()
    fs = list(db.execute(select(Finding)).unique().scalars())
    open_f = [f for f in fs if f.status in FINDING_OPEN_STATUSES]
    buckets = {"Not due": 0, "1-30 days": 0, "31-90 days": 0, "Over 90 days": 0}
    for f in open_f:
        d = (today - f.target_date).days if f.target_date else -1
        key = "Not due" if d <= 0 else ("1-30 days" if d <= 30 else ("31-90 days" if d <= 90 else "Over 90 days"))
        buckets[key] += 1
    by_sev_status = {}
    for f in fs:
        by_sev_status.setdefault(f.severity, {}).setdefault(f.status, 0)
        by_sev_status[f.severity][f.status] += 1
    closed = [f for f in fs if f.status == "Closed"]
    on_time = sum(1 for f in closed if f.closed_on and f.original_target_date and f.closed_on <= f.target_date)
    by_model = {}
    for f in open_f:
        by_model.setdefault(f.model.model_id, {"open": 0, "overdue": 0})
        by_model[f.model.model_id]["open"] += 1
        by_model[f.model.model_id]["overdue"] += int(svc.finding_overdue(f, today))
    return {"total": len(fs), "open": len(open_f), "overdue": sum(1 for f in open_f if svc.finding_overdue(f, today)),
            "open_critical": sum(1 for f in open_f if f.severity == "Critical"),
            "open_high": sum(1 for f in open_f if f.severity == "High"),
            "closed": len(closed), "closed_on_time": on_time,
            "risk_accepted": sum(1 for f in fs if f.status == "Risk Accepted"),
            "aging": buckets, "by_severity_status": by_sev_status, "by_model": by_model,
            "statuses": list(svc.FINDING_TRANSITIONS), "severities": Severity.values()}


@router.get("/findings/{finding_id}")
def get_finding(finding_id: str, db: Session = Depends(get_db), user: User = Depends(require("finding:read"))):
    return finding_out(db, svc.get_finding(db, finding_id), user, full=True)


class ResponseIn(BaseModel):
    management_response: str = Field(min_length=20, max_length=6000)
    action_plan: str = Field(min_length=20, max_length=6000)
    remediation_owner_id: int
    target_date: date


@router.post("/findings/{finding_id}/response")
def respond(finding_id: str, body: ResponseIn, db: Session = Depends(get_db),
            user: User = Depends(require("finding:respond"))):
    f = svc.get_finding(db, finding_id)
    svc.submit_response(db, user, f, body.model_dump(), get_settings().today())
    db.commit()
    db.refresh(f)
    return finding_out(db, f, user, full=True)


class FindingTransitionIn(BaseModel):
    to_status: str
    comment: str = Field("", max_length=4000)
    risk_acceptance_expiry: Optional[date] = None


@router.post("/findings/{finding_id}/transition")
def transition(finding_id: str, body: FindingTransitionIn, db: Session = Depends(get_db),
               user: User = Depends(require("finding:read"))):
    f = svc.get_finding(db, finding_id)
    svc.transition_finding(db, user, f, body.to_status, body.comment, get_settings().today(),
                           body.risk_acceptance_expiry)
    db.commit()
    db.refresh(f)
    return finding_out(db, f, user, full=True)


class ExtendIn(BaseModel):
    new_target_date: date
    justification: str = Field(min_length=20, max_length=2000)


@router.post("/findings/{finding_id}/extend")
def extend(finding_id: str, body: ExtendIn, db: Session = Depends(get_db),
           user: User = Depends(require("finding:extend"))):
    f = svc.get_finding(db, finding_id)
    svc.extend_finding(db, user, f, body.new_target_date, body.justification, get_settings().today())
    db.commit()
    db.refresh(f)
    return finding_out(db, f, user, full=True)


@router.post("/findings/{finding_id}/evidence", status_code=201)
async def add_evidence(finding_id: str, title: str = Form(..., min_length=3, max_length=200),
                       evidence_type: str = Form(..., min_length=3, max_length=48),
                       description: str = Form("", max_length=2000), file: Optional[UploadFile] = File(None),
                       db: Session = Depends(get_db), user: User = Depends(require("finding:read"))):
    f = svc.get_finding(db, finding_id)
    allowed = user.role == "admin" or svc.is_owner(user, f.model) or user.id == f.remediation_owner_id \
        or user.role == "validator"
    if not allowed:
        raise Forbidden("Only owners, the remediation owner or validators can add finding evidence")
    name, ctype, content = await _read_upload(file)
    ev = svc.store_evidence(db, user, "finding", f.id, f.finding_id, title, evidence_type, description, name, ctype,
                            content)
    db.commit()
    return evidence_out(ev)
