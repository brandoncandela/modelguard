from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.inventory import InventoryModel
from app.models.users import User


class Validation(Base):
    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    validation_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    scope_areas: Mapped[list] = mapped_column(JSON, default=list)
    scope_notes: Mapped[str] = mapped_column(Text, default="")
    lead_validator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    team: Mapped[list] = mapped_column(JSON, default=list)
    independence_attested: Mapped[bool] = mapped_column(Boolean, default=False)
    independence_statement: Mapped[str] = mapped_column(Text, default="")
    scheduled_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scheduled_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    submitted_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    decided_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    overall_rating: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    model: Mapped[InventoryModel] = relationship(lazy="joined")
    lead_validator: Mapped[Optional[User]] = relationship(lazy="joined")
    approvals: Mapped[list["ValidationApproval"]] = relationship(
        back_populates="validation", cascade="all, delete-orphan", order_by="ValidationApproval.decided_at"
    )
    findings: Mapped[list["Finding"]] = relationship(back_populates="validation", order_by="Finding.finding_id")


class ValidationApproval(Base):
    __tablename__ = "validation_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("validations.id", ondelete="CASCADE"), index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(32))
    comments: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime] = mapped_column(default=utcnow)

    validation: Mapped[Validation] = relationship(back_populates="approvals")
    approver: Mapped[User] = relationship(lazy="joined")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    validation_id: Mapped[int] = mapped_column(ForeignKey("validations.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    raised_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    raised_on: Mapped[date] = mapped_column(Date)
    management_response: Mapped[str] = mapped_column(Text, default="")
    action_plan: Mapped[str] = mapped_column(Text, default="")
    remediation_owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    original_target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    extension_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    risk_acceptance_rationale: Mapped[str] = mapped_column(Text, default="")
    risk_acceptance_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    validation: Mapped[Validation] = relationship(back_populates="findings")
    model: Mapped[InventoryModel] = relationship(lazy="joined")
    raised_by: Mapped[User] = relationship(foreign_keys=[raised_by_id], lazy="joined")
    remediation_owner: Mapped[Optional[User]] = relationship(foreign_keys=[remediation_owner_id], lazy="joined")
    closed_by: Mapped[Optional[User]] = relationship(foreign_keys=[closed_by_id], lazy="joined")


class Evidence(Base):
    """Evidence attached to a validation, finding or control. Files are stored by SHA-256."""

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(24))  # validation, finding, control
    entity_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    evidence_type: Mapped[str] = mapped_column(String(48))
    description: Mapped[str] = mapped_column(Text, default="")
    file_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow)

    uploaded_by: Mapped[User] = relationship(lazy="joined")


class WorkflowEvent(Base):
    """Status history for validations, findings and AI assessments (append-only by convention and service)."""

    __tablename__ = "workflow_events"
    __table_args__ = (Index("ix_wf_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(24))
    entity_id: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)

    actor: Mapped[User] = relationship(lazy="joined")
