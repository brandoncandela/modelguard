from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.users import User
from app.services import audit

router = APIRouter(tags=["audit"])


@router.get("/audit/events")
def events(
    entity_type: Optional[str] = Query(None, max_length=32),
    entity_ref: Optional[str] = Query(None, max_length=48),
    actor: Optional[str] = Query(None, max_length=64),
    action: Optional[str] = Query(None, max_length=48),
    q: Optional[str] = Query(None, max_length=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require("audit:read")),
):
    stmt = select(AuditEvent)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_ref:
        stmt = stmt.where(AuditEvent.entity_ref == entity_ref)
    if actor:
        stmt = stmt.where(AuditEvent.actor_username == actor)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if q:
        stmt = stmt.where(AuditEvent.summary.ilike(f"%{q}%"))
    if date_from:
        stmt = stmt.where(AuditEvent.occurred_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AuditEvent.occurred_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    items = [{"id": e.id, "event_id": e.event_id, "occurred_at": e.occurred_at, "actor": e.actor_username,
              "role": e.actor_role, "action": e.action, "entity_type": e.entity_type, "entity_ref": e.entity_ref,
              "summary": e.summary, "changes": e.changes, "request_id": e.request_id, "hash": e.hash,
              "prev_hash": e.prev_hash} for e in rows]
    actions = sorted(db.execute(select(AuditEvent.action).distinct()).scalars())
    types = sorted(db.execute(select(AuditEvent.entity_type).distinct()).scalars())
    return {"items": items, "total": total, "page": page, "page_size": page_size, "actions": actions,
            "entity_types": types}


@router.get("/audit/verify")
def verify(db: Session = Depends(get_db), _: User = Depends(require("audit:read"))):
    return audit.verify_chain(db)
