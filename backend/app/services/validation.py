"""Module C: independent validation workflow, findings lifecycle and evidence.

Rules enforced here (and documented in VALIDATION_METHODOLOGY.md):
  - Validators must be independent of the model: never its business owner or model risk owner.
  - The approver of a validation cannot be its lead validator or a team member.
  - One active validation per model at a time.
  - Submission for review needs a rating, a written summary and at least one evidence item.
  - Approval is blocked while Critical or High findings from the validation are open.
    Conditional approval needs written conditions and is blocked by open Critical findings
    that have no accepted remediation plan.
  - Findings close only after remediation evidence is reviewed by a validator who is not the
    remediation owner. Critical findings cannot be risk-accepted.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import (
    FINDING_OPEN_STATUSES,
    VALIDATION_CYCLE_MONTHS,
    VALIDATION_SCOPE_AREAS,
    FindingCategory,
    FindingStatus,
    Severity,
    ValidationStatus,
    ValidationType,
)
from app.core.errors import Conflict, Forbidden, NotFound, WorkflowError
from app.models.inventory import InventoryModel
from app.models.users import User
from app.models.validation import Evidence, Finding, Validation, ValidationApproval, WorkflowEvent
from app.services import audit
from app.services.inventory import add_months

VS = ValidationStatus
FS = FindingStatus
ACTIVE_VALIDATION = [VS.NOT_STARTED.value, VS.SCHEDULED.value, VS.IN_PROGRESS.value, VS.PENDING_REVIEW.value]
DECIDED = [VS.APPROVED.value, VS.CONDITIONALLY_APPROVED.value, VS.REJECTED.value]
TARGET_DAYS = {"Critical": 60, "High": 90, "Medium": 180, "Low": 270}
RATINGS = ["Satisfactory", "Satisfactory with recommendations", "Needs improvement", "Unsatisfactory"]

VALIDATION_TRANSITIONS = {
    VS.NOT_STARTED.value: [VS.SCHEDULED.value],
    VS.SCHEDULED.value: [VS.IN_PROGRESS.value, VS.NOT_STARTED.value],
    VS.IN_PROGRESS.value: [VS.PENDING_REVIEW.value],
    VS.PENDING_REVIEW.value: [VS.APPROVED.value, VS.CONDITIONALLY_APPROVED.value, VS.REJECTED.value,
                              VS.IN_PROGRESS.value],
    VS.APPROVED.value: [],
    VS.CONDITIONALLY_APPROVED.value: [],
    VS.REJECTED.value: [],
}

FINDING_TRANSITIONS = {
    FS.OPEN.value: [FS.RESPONSE_SUBMITTED.value, FS.RISK_ACCEPTED.value],
    FS.RESPONSE_SUBMITTED.value: [FS.IN_REMEDIATION.value, FS.OPEN.value, FS.RISK_ACCEPTED.value],
    FS.IN_REMEDIATION.value: [FS.PENDING_VALIDATION.value, FS.RISK_ACCEPTED.value],
    FS.PENDING_VALIDATION.value: [FS.CLOSED.value, FS.IN_REMEDIATION.value],
    FS.CLOSED.value: [],
    FS.RISK_ACCEPTED.value: [],
}

ALLOWED_TYPES = {
    "application/pdf": ".pdf", "text/csv": ".csv", "text/plain": ".txt", "application/json": ".json",
    "image/png": ".png", "image/jpeg": ".jpg",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


def _event(db: Session, entity_type: str, entity_id: int, event_type: str, actor: User, frm=None, to=None,
           comment: str = "", data: Optional[dict] = None, at: Optional[datetime] = None) -> WorkflowEvent:
    ev = WorkflowEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type, from_status=frm,
                       to_status=to, actor_id=actor.id, comment=comment, data=audit.canonical(data or {}),
                       occurred_at=at or datetime.now(timezone.utc))
    db.add(ev)
    return ev


def get_validation(db: Session, validation_id: str) -> Validation:
    v = db.execute(select(Validation).where(Validation.validation_id == validation_id)).unique().scalar_one_or_none()
    if v is None:
        raise NotFound(f"Validation {validation_id} not found")
    return v


def get_finding(db: Session, finding_id: str) -> Finding:
    f = db.execute(select(Finding).where(Finding.finding_id == finding_id)).unique().scalar_one_or_none()
    if f is None:
        raise NotFound(f"Finding {finding_id} not found")
    return f


def is_owner(user: User, model: InventoryModel) -> bool:
    return user.id in (model.business_owner_id, model.model_risk_owner_id)


def team_ids(v: Validation) -> List[int]:
    ids = [int(x) for x in (v.team or [])]
    if v.lead_validator_id:
        ids.append(v.lead_validator_id)
    return ids


def check_independent(db: Session, model: InventoryModel, user_ids: List[int]) -> None:
    for uid in user_ids:
        u = db.get(User, uid)
        if u is None or not u.is_active:
            raise WorkflowError(f"User {uid} not found or inactive")
        if u.role != "validator":
            raise WorkflowError(f"{u.full_name} is not a validator")
        if uid in (model.business_owner_id, model.model_risk_owner_id):
            raise WorkflowError(f"{u.full_name} owns {model.model_id} and cannot validate it")


def next_validation_id(db: Session, year: int) -> str:
    n = db.execute(select(func.count()).select_from(Validation).where(
        Validation.validation_id.like(f"VAL-{year}-%"))).scalar()
    return f"VAL-{year}-{n + 1:03d}"


def next_finding_id(db: Session, year: int) -> str:
    n = db.execute(select(func.count()).select_from(Finding).where(Finding.finding_id.like(f"FND-{year}-%"))).scalar()
    return f"FND-{year}-{n + 1:03d}"


def open_findings(db: Session, validation: Validation, severities: List[str]) -> List[Finding]:
    return list(db.execute(select(Finding).where(Finding.validation_id == validation.id,
                                                 Finding.severity.in_(severities),
                                                 Finding.status.in_(FINDING_OPEN_STATUSES))).unique().scalars())


def finding_overdue(f: Finding, today: date) -> bool:
    return f.status in FINDING_OPEN_STATUSES and f.target_date is not None and f.target_date < today


# ---------------------------------------------------------------------------------------------
# validations
# ---------------------------------------------------------------------------------------------


def create_validation(db: Session, user: User, data: Dict[str, Any], today: date) -> Validation:
    model = db.execute(select(InventoryModel).where(InventoryModel.model_id == data["model_id"])).unique().scalar_one_or_none()
    if model is None:
        raise NotFound(f"Model {data['model_id']} not found")
    if model.is_archived:
        raise WorkflowError("Cannot validate an archived model")
    active = db.execute(select(Validation.validation_id).where(Validation.model_id == model.id,
                                                               Validation.status.in_(ACTIVE_VALIDATION))).scalar()
    if active:
        raise Conflict(f"{model.model_id} already has an active validation ({active})")
    if data["validation_type"] not in ValidationType.values():
        raise WorkflowError("Unknown validation type")
    bad = set(data.get("scope_areas") or []) - set(VALIDATION_SCOPE_AREAS)
    if bad:
        raise WorkflowError(f"Unknown scope areas: {sorted(bad)}")
    ids = ([data["lead_validator_id"]] if data.get("lead_validator_id") else []) + list(data.get("team") or [])
    check_independent(db, model, ids)
    v = Validation(validation_id=next_validation_id(db, today.year), model_id=model.id,
                   validation_type=data["validation_type"], status=VS.NOT_STARTED.value,
                   scope_areas=data.get("scope_areas") or [], scope_notes=data.get("scope_notes") or "",
                   lead_validator_id=data.get("lead_validator_id"), team=list(data.get("team") or []),
                   scheduled_start=data.get("scheduled_start"), scheduled_end=data.get("scheduled_end"))
    db.add(v)
    db.flush()
    _event(db, "validation", v.id, "CREATED", user, None, v.status, data.get("scope_notes", ""))
    audit.record(db, user.username, user.role, "VALIDATION_CREATED", "validation", v.validation_id,
                 f"{v.validation_type} validation of {model.model_id} created",
                 {"model_id": model.model_id, "scope_areas": v.scope_areas})
    return v


EDITABLE_VALIDATION = {
    "planning": ["scope_areas", "scope_notes", "lead_validator_id", "team", "scheduled_start", "scheduled_end",
                 "validation_type"],
    "fieldwork": ["scope_notes", "overall_rating", "summary", "independence_attested", "independence_statement", "team"],
}


def update_validation(db: Session, user: User, v: Validation, changes: Dict[str, Any]) -> Validation:
    if v.status in (VS.NOT_STARTED.value, VS.SCHEDULED.value):
        if user.role in ("admin", "compliance_reviewer"):
            allowed = EDITABLE_VALIDATION["planning"]
        elif v.status == VS.SCHEDULED.value and user.id == v.lead_validator_id:
            allowed = ["independence_attested", "independence_statement"]
        else:
            raise Forbidden("Planning fields are set by Model Risk Management (administrator or compliance reviewer)")
    elif v.status == VS.IN_PROGRESS.value:
        if user.id not in team_ids(v) and user.role != "admin":
            raise Forbidden("Only the assigned validation team can edit fieldwork")
        allowed = EDITABLE_VALIDATION["fieldwork"]
    else:
        raise WorkflowError(f"A validation in '{v.status}' cannot be edited")
    illegal = set(changes) - set(allowed)
    if illegal:
        raise WorkflowError(f"Cannot change {sorted(illegal)} while the validation is '{v.status}'")
    if "scope_areas" in changes:
        bad = set(changes["scope_areas"] or []) - set(VALIDATION_SCOPE_AREAS)
        if bad:
            raise WorkflowError(f"Unknown scope areas: {sorted(bad)}")
    if "overall_rating" in changes and changes["overall_rating"] not in RATINGS + [None]:
        raise WorkflowError(f"overall_rating must be one of {RATINGS}")
    if "lead_validator_id" in changes or "team" in changes:
        ids = [changes.get("lead_validator_id", v.lead_validator_id)] + list(changes.get("team", v.team) or [])
        check_independent(db, v.model, [i for i in ids if i])
    before = {k: getattr(v, k) for k in changes}
    for k, val in changes.items():
        setattr(v, k, val)
    delta = audit.diff(before, {k: getattr(v, k) for k in changes})
    if delta:
        _event(db, "validation", v.id, "UPDATED", user, v.status, v.status, data=delta)
        audit.record(db, user.username, user.role, "VALIDATION_UPDATED", "validation", v.validation_id,
                     f"Updated {', '.join(sorted(delta))}", delta)
    return v


def evidence_count(db: Session, entity_type: str, entity_id: int) -> int:
    return db.execute(select(func.count()).select_from(Evidence).where(
        Evidence.entity_type == entity_type, Evidence.entity_id == entity_id)).scalar()


def transition_validation(db: Session, user: User, v: Validation, to: str, comment: str = "",
                          conditions: str = "", today: Optional[date] = None) -> Validation:
    today = today or get_settings().today()
    frm = v.status
    if to not in VALIDATION_TRANSITIONS.get(frm, []):
        raise WorkflowError(f"Cannot move a validation from '{frm}' to '{to}'",
                            {"allowed": VALIDATION_TRANSITIONS.get(frm, [])})
    model = v.model
    if to in (VS.SCHEDULED.value, VS.NOT_STARTED.value) and frm in (VS.NOT_STARTED.value, VS.SCHEDULED.value):
        if user.role not in ("admin", "compliance_reviewer"):
            raise Forbidden("Scheduling is done by Model Risk Management")
        if to == VS.SCHEDULED.value:
            missing = [f for f in ("lead_validator_id", "scheduled_start", "scheduled_end") if not getattr(v, f)]
            if not v.scope_areas:
                missing.append("scope_areas")
            if missing:
                raise WorkflowError(f"Set {', '.join(missing)} before scheduling")
            if v.scheduled_end < v.scheduled_start:
                raise WorkflowError("scheduled_end must be after scheduled_start")
    elif to == VS.IN_PROGRESS.value and frm == VS.SCHEDULED.value:
        if user.id != v.lead_validator_id:
            raise Forbidden("Only the lead validator can start fieldwork")
        check_independent(db, model, team_ids(v))
        if not v.independence_attested:
            raise WorkflowError("The lead validator must attest independence before starting")
        v.actual_start = today
    elif to == VS.PENDING_REVIEW.value:
        if user.id != v.lead_validator_id:
            raise Forbidden("Only the lead validator can submit for review")
        missing = []
        if not v.overall_rating:
            missing.append("an overall rating")
        if len((v.summary or "").strip()) < 50:
            missing.append("a summary of at least 50 characters")
        if evidence_count(db, "validation", v.id) == 0:
            missing.append("at least one evidence item")
        if missing:
            raise WorkflowError(f"Before submitting add {', '.join(missing)}")
        v.submitted_on = today
    elif frm == VS.PENDING_REVIEW.value:
        if user.role not in ("admin", "compliance_reviewer"):
            raise Forbidden("Only the approval authority can decide on a validation")
        if user.id in team_ids(v):
            raise Forbidden("An approver cannot have worked on the validation")
        if is_owner(user, model):
            raise Forbidden("A model owner cannot approve their own model's validation")
        if to == VS.IN_PROGRESS.value:
            if len(comment.strip()) < 10:
                raise WorkflowError("Explain what must be reworked (at least 10 characters)")
            v.submitted_on = None
        else:
            if to == VS.APPROVED.value:
                blocking = open_findings(db, v, ["Critical", "High"])
                if blocking:
                    raise WorkflowError("Open Critical or High findings block full approval; use Conditionally "
                                        "Approved with conditions, or close them first",
                                        {"findings": [f.finding_id for f in blocking]})
            if to == VS.CONDITIONALLY_APPROVED.value:
                if len(conditions.strip()) < 20:
                    raise WorkflowError("Conditional approval needs written conditions (at least 20 characters)")
                blocking = [f for f in open_findings(db, v, ["Critical"]) if f.status == FS.OPEN.value]
                if blocking:
                    raise WorkflowError("Critical findings without an accepted remediation plan block approval",
                                        {"findings": [f.finding_id for f in blocking]})
                v.conditions = conditions.strip()
            if to == VS.REJECTED.value and len(comment.strip()) < 10:
                raise WorkflowError("Give the reason for rejection (at least 10 characters)")
            v.decided_on = today
            db.add(ValidationApproval(validation_id=v.id, approver_id=user.id, decision=to, comments=comment,
                                      conditions=conditions))
            _apply_decision_to_model(db, user, v, model, to, today)
    v.status = to
    _event(db, "validation", v.id, "STATUS_CHANGE", user, frm, to, comment,
           {"conditions": conditions} if conditions else None)
    audit.record(db, user.username, user.role, "VALIDATION_APPROVAL" if frm == VS.PENDING_REVIEW.value and to in DECIDED
                 else "VALIDATION_STATUS", "validation", v.validation_id,
                 f"{v.validation_id} ({model.model_id}): {frm} to {to}" + (f". {comment}" if comment else ""),
                 {"status": {"from": frm, "to": to}, "comment": comment, "conditions": conditions})
    return v


def _apply_decision_to_model(db: Session, user: User, v: Validation, model: InventoryModel, decision: str,
                             today: date) -> None:
    before = {"approval_status": model.approval_status, "last_validation_date": model.last_validation_date,
              "next_validation_date": model.next_validation_date, "lifecycle_stage": model.lifecycle_stage}
    if decision in (VS.APPROVED.value, VS.CONDITIONALLY_APPROVED.value):
        model.approval_status = decision
        model.last_validation_date = today
        model.next_validation_date = add_months(today, VALIDATION_CYCLE_MONTHS[model.risk_rating])
        if v.validation_type == ValidationType.INITIAL.value and model.lifecycle_stage in (
                "Development", "Pre-Implementation Validation"):
            model.lifecycle_stage = "Production"
    else:
        model.approval_status = "Not Approved"
        if model.lifecycle_stage == "Production":
            model.lifecycle_stage = "Under Remediation"
    after = {k: getattr(model, k) for k in before}
    delta = audit.diff(before, after)
    if delta:
        audit.record(db, user.username, user.role, "MODEL_APPROVAL_UPDATED", "model", model.model_id,
                     f"Validation {v.validation_id} decision: {decision}", delta)


# ---------------------------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._ -]")


def store_evidence(db: Session, user: User, entity_type: str, entity_id: int, entity_ref: str, title: str,
                   evidence_type: str, description: str, file_name: Optional[str] = None,
                   content_type: Optional[str] = None, content: Optional[bytes] = None,
                   at: Optional[datetime] = None, write_audit: bool = True) -> Evidence:
    sha = size = key = None
    clean_name = None
    if content is not None:
        if len(content) == 0:
            raise WorkflowError("Uploaded file is empty")
        if len(content) > MAX_EVIDENCE_BYTES:
            raise WorkflowError("Evidence files are limited to 10 MB")
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct not in ALLOWED_TYPES:
            raise WorkflowError(f"File type '{ct}' is not accepted", {"accepted": sorted(ALLOWED_TYPES)})
        clean_name = _SAFE.sub("_", Path(file_name or "evidence").name)[:120] or "evidence"
        sha = hashlib.sha256(content).hexdigest()
        size = len(content)
        key = f"evidence/{sha[:2]}/{sha}"
        path = get_settings().data_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        content_type = ct
    n = db.execute(select(func.count()).select_from(Evidence)).scalar()
    ev = Evidence(evidence_id=f"EVD-{n + 1:05d}", entity_type=entity_type, entity_id=entity_id, title=title,
                  evidence_type=evidence_type, description=description, file_name=clean_name,
                  content_type=content_type, file_size=size, sha256=sha, storage_key=key, uploaded_by_id=user.id,
                  uploaded_at=at or datetime.now(timezone.utc))
    db.add(ev)
    db.flush()
    if write_audit:
        audit.record(db, user.username, user.role, "EVIDENCE_ADDED", entity_type, entity_ref,
                     f"Evidence {ev.evidence_id}: {title}", {"evidence_id": ev.evidence_id, "sha256": sha,
                                                             "file_name": clean_name, "size": size})
    return ev


def evidence_path(ev: Evidence) -> Path:
    if not ev.storage_key:
        raise NotFound("This evidence item has no file")
    p = get_settings().data_path / ev.storage_key
    if not p.exists():
        raise NotFound("Evidence file missing from storage")
    if hashlib.sha256(p.read_bytes()).hexdigest() != ev.sha256:
        raise WorkflowError("Stored file does not match its recorded SHA-256; it may have been altered")
    return p


def can_add_validation_evidence(user: User, v: Validation) -> None:
    if v.status not in (VS.IN_PROGRESS.value, VS.PENDING_REVIEW.value):
        raise WorkflowError(f"Evidence can be added while In Progress or Pending Review, not '{v.status}'")
    if user.id not in team_ids(v) and user.role != "admin":
        raise Forbidden("Only the validation team can add validation evidence")


# ---------------------------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------------------------


def create_finding(db: Session, user: User, v: Validation, data: Dict[str, Any], today: date) -> Finding:
    if user.id not in team_ids(v):
        raise Forbidden("Only the validation team can raise findings on this validation")
    if v.status not in (VS.IN_PROGRESS.value, VS.PENDING_REVIEW.value):
        raise WorkflowError("Findings are raised during fieldwork or review")
    if data["severity"] not in Severity.values():
        raise WorkflowError("Unknown severity")
    if data["category"] not in FindingCategory.values():
        raise WorkflowError("Unknown category")
    model = v.model
    target = data.get("target_date") or today + timedelta(days=TARGET_DAYS[data["severity"]])
    owner_id = data.get("remediation_owner_id") or model.model_risk_owner_id
    f = Finding(finding_id=next_finding_id(db, today.year), validation_id=v.id, model_id=model.id,
                title=data["title"], description=data["description"], category=data["category"],
                severity=data["severity"], status=FS.OPEN.value, raised_by_id=user.id, raised_on=today,
                remediation_owner_id=owner_id, target_date=target, original_target_date=target)
    db.add(f)
    db.flush()
    _event(db, "finding", f.id, "RAISED", user, None, f.status, data["description"][:500],
           {"severity": f.severity, "target_date": str(target)})
    audit.record(db, user.username, user.role, "FINDING_RAISED", "finding", f.finding_id,
                 f"{f.severity} finding on {model.model_id}: {f.title}",
                 {"severity": f.severity, "category": f.category, "target_date": str(target)})
    return f


def submit_response(db: Session, user: User, f: Finding, data: Dict[str, Any], today: date) -> Finding:
    model = f.model
    if user.role != "admin" and not (is_owner(user, model) or user.id == f.remediation_owner_id):
        raise Forbidden("Only the model's owners or the remediation owner can respond")
    if f.status not in (FS.OPEN.value, FS.RESPONSE_SUBMITTED.value):
        raise WorkflowError(f"A response can be submitted while Open or Response Submitted, not '{f.status}'")
    owner = db.get(User, data["remediation_owner_id"])
    if owner is None or owner.role not in ("model_owner", "admin"):
        raise WorkflowError("The remediation owner must be a model owner")
    if data["target_date"] < today:
        raise WorkflowError("Target date cannot be in the past")
    if data["target_date"] > (f.original_target_date or data["target_date"]) and f.status == FS.OPEN.value:
        raise WorkflowError("A later target date than policy allows needs an approved extension")
    frm = f.status
    f.management_response = data["management_response"]
    f.action_plan = data["action_plan"]
    f.remediation_owner_id = owner.id
    f.target_date = data["target_date"]
    f.status = FS.RESPONSE_SUBMITTED.value
    _event(db, "finding", f.id, "RESPONSE", user, frm, f.status, data["management_response"][:500],
           {"action_plan": data["action_plan"], "target_date": str(data["target_date"]), "owner": owner.username})
    audit.record(db, user.username, user.role, "FINDING_RESPONSE", "finding", f.finding_id,
                 f"Management response submitted (owner {owner.full_name}, target {data['target_date']})",
                 {"status": {"from": frm, "to": f.status}, "target_date": str(data["target_date"])})
    return f


def transition_finding(db: Session, user: User, f: Finding, to: str, comment: str, today: date,
                       risk_acceptance_expiry: Optional[date] = None) -> Finding:
    frm = f.status
    if to not in FINDING_TRANSITIONS.get(frm, []):
        raise WorkflowError(f"Cannot move a finding from '{frm}' to '{to}'",
                            {"allowed": FINDING_TRANSITIONS.get(frm, [])})
    model = f.model
    if to == FS.RESPONSE_SUBMITTED.value:
        raise WorkflowError("Use the response endpoint to submit a management response")
    if frm == FS.RESPONSE_SUBMITTED.value and to in (FS.IN_REMEDIATION.value, FS.OPEN.value):
        if user.role != "validator" or is_owner(user, model):
            raise Forbidden("An independent validator accepts or rejects management responses")
        if to == FS.OPEN.value and len(comment.strip()) < 10:
            raise WorkflowError("Explain why the response is not accepted")
    elif to == FS.PENDING_VALIDATION.value:
        if user.role != "admin" and not (is_owner(user, model) or user.id == f.remediation_owner_id):
            raise Forbidden("The remediation owner submits remediation for validation")
        if evidence_count(db, "finding", f.id) == 0:
            raise WorkflowError("Attach remediation evidence before submitting for validation")
    elif frm == FS.PENDING_VALIDATION.value:
        if user.role != "validator":
            raise Forbidden("A validator verifies remediation")
        if user.id == f.remediation_owner_id or is_owner(user, model):
            raise Forbidden("The person who remediated cannot close the finding")
        if to == FS.IN_REMEDIATION.value and len(comment.strip()) < 10:
            raise WorkflowError("Explain why the remediation is not sufficient")
        if to == FS.CLOSED.value:
            f.closed_on = today
            f.closed_by_id = user.id
    elif to == FS.RISK_ACCEPTED.value:
        if user.role not in ("admin", "compliance_reviewer"):
            raise Forbidden("Risk acceptance needs the approval authority")
        if f.severity == "Critical":
            raise WorkflowError("Critical findings cannot be risk-accepted under MRM-POL-001")
        if len(comment.strip()) < 20:
            raise WorkflowError("Risk acceptance needs a rationale of at least 20 characters")
        if risk_acceptance_expiry is None or not (today < risk_acceptance_expiry <= today + timedelta(days=365)):
            raise WorkflowError("Risk acceptance needs an expiry date within the next 12 months")
        f.risk_acceptance_rationale = comment
        f.risk_acceptance_expiry = risk_acceptance_expiry
    f.status = to
    _event(db, "finding", f.id, "STATUS_CHANGE", user, frm, to, comment,
           {"risk_acceptance_expiry": str(risk_acceptance_expiry)} if risk_acceptance_expiry else None)
    audit.record(db, user.username, user.role, "FINDING_CLOSED" if to == FS.CLOSED.value else
                 ("FINDING_RISK_ACCEPTED" if to == FS.RISK_ACCEPTED.value else "FINDING_STATUS"), "finding",
                 f.finding_id, f"{f.finding_id}: {frm} to {to}" + (f". {comment[:200]}" if comment else ""),
                 {"status": {"from": frm, "to": to}, "comment": comment})
    return f


def extend_finding(db: Session, user: User, f: Finding, new_date: date, justification: str, today: date) -> Finding:
    if f.status not in FINDING_OPEN_STATUSES:
        raise WorkflowError("Only open findings can be extended")
    if f.target_date and new_date <= f.target_date:
        raise WorkflowError("The new target date must be later than the current one")
    if new_date <= today:
        raise WorkflowError("The new target date must be in the future")
    if len(justification.strip()) < 20:
        raise WorkflowError("Extensions need a justification of at least 20 characters")
    if f.extension_count >= 2 and user.role != "admin":
        raise WorkflowError("A third extension needs administrator approval and committee notification")
    old = f.target_date
    f.target_date = new_date
    f.extension_count += 1
    _event(db, "finding", f.id, "EXTENSION", user, f.status, f.status, justification,
           {"from": str(old), "to": str(new_date), "extension": f.extension_count})
    audit.record(db, user.username, user.role, "FINDING_EXTENDED", "finding", f.finding_id,
                 f"Target date {old} to {new_date} (extension {f.extension_count})",
                 {"target_date": {"from": str(old), "to": str(new_date)}, "justification": justification})
    return f
