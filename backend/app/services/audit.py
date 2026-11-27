"""Append-only, hash-chained audit trail.

Each event stores the SHA-256 of the previous event's hash plus its own canonical content, so any
edit, deletion or reordering breaks verification. Writes are serialised (PostgreSQL advisory lock,
process lock on SQLite) and `prev_hash` is unique, so the chain cannot fork.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models.audit import AuditEvent

GENESIS = "0" * 64
_lock = threading.Lock()


class AuditImmutableError(RuntimeError):
    pass


@event.listens_for(AuditEvent, "before_update")
def _block_update(mapper, connection, target):  # pragma: no cover - guard
    raise AuditImmutableError("audit_events is append-only")


@event.listens_for(AuditEvent, "before_delete")
def _block_delete(mapper, connection, target):  # pragma: no cover - guard
    raise AuditImmutableError("audit_events is append-only")


def _ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical(changes: Any) -> Any:
    return json.loads(json.dumps(changes or {}, default=str, sort_keys=True))


def compute_hash(prev_hash: str, e: Dict[str, Any]) -> str:
    body = {
        "prev_hash": prev_hash,
        "event_id": e["event_id"],
        "occurred_at": _ts(e["occurred_at"]),
        "actor_username": e["actor_username"],
        "actor_role": e["actor_role"],
        "action": e["action"],
        "entity_type": e["entity_type"],
        "entity_ref": e["entity_ref"],
        "summary": e["summary"],
        "changes": e["changes"],
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record(db: Session, actor_username: str, actor_role: str, action: str, entity_type: str, entity_ref: str,
           summary: str, changes: Optional[Dict[str, Any]] = None, ip_address: Optional[str] = None,
           occurred_at: Optional[datetime] = None) -> AuditEvent:
    """Append one audit event in the caller's transaction."""
    with _lock:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(504117)"))
        last = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar()
        prev = last or GENESIS
        data = {
            "event_id": str(uuid.uuid4()),
            "occurred_at": occurred_at or datetime.now(timezone.utc),
            "actor_username": actor_username,
            "actor_role": actor_role,
            "action": action,
            "entity_type": entity_type,
            "entity_ref": entity_ref,
            "summary": summary,
            "changes": canonical(changes),
        }
        ev = AuditEvent(**data, request_id=request_id_var.get(), ip_address=ip_address, prev_hash=prev,
                        hash=compute_hash(prev, data))
        db.add(ev)
        db.flush()
        return ev


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k), after.get(k)
        if canonical({"v": b}) != canonical({"v": a}):
            out[k] = {"from": b, "to": a}
    return canonical(out)


def verify_chain(db: Session) -> Dict[str, Any]:
    prev = GENESIS
    count = 0
    broken: List[Dict[str, Any]] = []
    for ev in db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        count += 1
        data = {k: getattr(ev, k) for k in ("event_id", "occurred_at", "actor_username", "actor_role", "action",
                                             "entity_type", "entity_ref", "summary", "changes")}
        expected = compute_hash(prev, data)
        if ev.prev_hash != prev or ev.hash != expected:
            broken.append({"id": ev.id, "event_id": ev.event_id, "expected_prev": prev, "stored_prev": ev.prev_hash})
            if len(broken) >= 20:
                break
        prev = ev.hash
    return {"events_checked": count, "valid": not broken, "breaks": broken, "head_hash": prev}
