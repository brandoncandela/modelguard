from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.config import get_settings
from app.core.enums import (
    DOCUMENTATION_ARTIFACTS,
    ApprovalStatus,
    DocumentationStatus,
    LifecycleStage,
    MethodologyType,
    ModelCategory,
    MonitoringFrequency,
    SupervisoryClass,
)
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.inventory import InventoryModel
from app.models.users import User
from app.schemas.common import Page
from app.schemas.inventory import ArchiveRequest, Facets, ModelCreate, ModelDetail, ModelOut, ModelUpdate
from app.services import inventory as svc

router = APIRouter(tags=["inventory"])


@router.get("/models", response_model=Page[ModelOut])
def list_models(
    q: Optional[str] = Query(None, max_length=100, description="Search ID, name, methodology, limitations, owners"),
    category: Optional[List[str]] = Query(None),
    risk_rating: Optional[List[str]] = Query(None),
    lifecycle_stage: Optional[List[str]] = Query(None),
    approval_status: Optional[List[str]] = Query(None),
    business_unit: Optional[List[str]] = Query(None),
    documentation_status: Optional[List[str]] = Query(None),
    validation_due: Optional[str] = Query(None, pattern="^(overdue|due_90d)$"),
    include_archived: bool = False,
    archived_only: bool = False,
    sort: str = Query("model_id", pattern="^(" + "|".join(svc.SORTABLE) + ")$"),
    direction: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require("inventory:read")),
):
    today = get_settings().today()
    items, total = svc.list_models(db, q=q, category=category, risk_rating=risk_rating, lifecycle_stage=lifecycle_stage,
                                   approval_status=approval_status, business_unit=business_unit,
                                   documentation_status=documentation_status, validation_due=validation_due,
                                   include_archived=include_archived, archived_only=archived_only, sort=sort,
                                   direction=direction, page=page, page_size=page_size, today=today)
    return {"items": svc.to_out(db, items, today), "total": total, "page": page, "page_size": page_size}


@router.get("/models/facets", response_model=Facets)
def facets(db: Session = Depends(get_db), _: User = Depends(require("inventory:read"))):
    bus = sorted(set(db.execute(select(InventoryModel.business_unit)).scalars()))
    return Facets(categories=ModelCategory.values(), risk_ratings=["High", "Medium", "Low"],
                  lifecycle_stages=LifecycleStage.values(), approval_statuses=ApprovalStatus.values(),
                  documentation_statuses=DocumentationStatus.values(), business_units=bus,
                  methodology_types=MethodologyType.values(), monitoring_frequencies=MonitoringFrequency.values(),
                  documentation_artifacts=DOCUMENTATION_ARTIFACTS,
                  supervisory_classifications=SupervisoryClass.values())


@router.post("/models", response_model=ModelDetail, status_code=201)
def create_model(body: ModelCreate, db: Session = Depends(get_db), user: User = Depends(require("inventory:create"))):
    today = get_settings().today()
    m = svc.create_model(db, user, body.model_dump(), today)
    db.commit()
    return svc.to_out(db, [svc.get_model(db, m.model_id)], today, user)[0]


@router.get("/models/{model_id}", response_model=ModelDetail)
def get_model(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("inventory:read"))):
    return svc.to_out(db, [svc.get_model(db, model_id)], get_settings().today(), user)[0]


@router.patch("/models/{model_id}", response_model=ModelDetail)
def update_model(model_id: str, body: ModelUpdate, db: Session = Depends(get_db),
                 user: User = Depends(require("inventory:edit"))):
    today = get_settings().today()
    m = svc.get_model(db, model_id)
    svc.update_model(db, user, m, body.model_dump(exclude_unset=True), today)
    db.commit()
    db.refresh(m)
    return svc.to_out(db, [m], today, user)[0]


@router.post("/models/{model_id}/archive", response_model=ModelDetail)
def archive_model(model_id: str, body: ArchiveRequest, db: Session = Depends(get_db),
                  user: User = Depends(require("inventory:archive"))):
    m = svc.get_model(db, model_id)
    svc.archive_model(db, user, m, body.reason)
    db.commit()
    return svc.to_out(db, [m], get_settings().today(), user)[0]


@router.post("/models/{model_id}/restore", response_model=ModelDetail)
def restore_model(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("inventory:archive"))):
    m = svc.get_model(db, model_id)
    svc.restore_model(db, user, m)
    db.commit()
    return svc.to_out(db, [m], get_settings().today(), user)[0]


@router.get("/models/{model_id}/history")
def model_history(model_id: str, db: Session = Depends(get_db), _: User = Depends(require("inventory:read"))):
    svc.get_model(db, model_id)
    rows = db.execute(select(AuditEvent).where(AuditEvent.entity_type == "model", AuditEvent.entity_ref == model_id)
                      .order_by(AuditEvent.id.desc()).limit(200)).scalars()
    return [{"occurred_at": e.occurred_at, "actor": e.actor_username, "role": e.actor_role, "action": e.action,
             "summary": e.summary, "changes": e.changes} for e in rows]
