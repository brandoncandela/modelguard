"""Audit trail: hash chain verification, tamper detection and database-level append-only triggers."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.services import audit


def test_seed_chain_is_valid(db):
    result = audit.verify_chain(db)
    assert result["valid"] is True
    assert result["events_checked"] >= 10


def test_record_extends_chain(db):
    before = audit.verify_chain(db)
    ev = audit.record(db, "tester", "admin", "TEST_EVENT", "test", "T-1", "unit test", {"a": 1})
    db.commit()
    assert ev.prev_hash == before["head_hash"]
    after = audit.verify_chain(db)
    assert after["valid"] and after["events_checked"] == before["events_checked"] + 1


def test_database_blocks_update_and_delete(db):
    with pytest.raises((DatabaseError, IntegrityError)):
        db.execute(text("UPDATE audit_events SET summary = 'tampered' WHERE id = 1"))
    db.rollback()
    with pytest.raises((DatabaseError, IntegrityError)):
        db.execute(text("DELETE FROM audit_events WHERE id = 1"))
    db.rollback()


def test_tampering_is_detected(db):
    """Simulate an attacker who bypasses the trigger: verification must flag the broken link."""
    if db.bind.dialect.name != "sqlite":
        pytest.skip("trigger bypass simulated on SQLite only")
    db.execute(text("DROP TRIGGER audit_events_no_update"))
    db.execute(text("UPDATE audit_events SET summary = 'tampered' WHERE id = 2"))
    db.commit()
    result = audit.verify_chain(db)
    assert result["valid"] is False
    assert result["breaks"][0]["id"] == 2


def test_diff_only_reports_changes():
    assert audit.diff({"a": 1, "b": "x"}, {"a": 1, "b": "y"}) == {"b": {"from": "x", "to": "y"}}
