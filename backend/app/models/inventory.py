from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.users import User


class InventoryModel(Base):
    """One row per model in the enterprise model inventory (Module A)."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    business_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    model_risk_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    developer: Mapped[str] = mapped_column(String(120), default="")
    business_unit: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    methodology: Mapped[str] = mapped_column(Text)
    methodology_type: Mapped[str] = mapped_column(String(40))
    vendor: Mapped[str] = mapped_column(String(80), default="In-house")
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    geographies: Mapped[list] = mapped_column(JSON, default=list)
    risk_rating: Mapped[str] = mapped_column(String(10), index=True)
    risk_rationale: Mapped[str] = mapped_column(Text, default="")
    # The bank's determination of whether the April 2026 interagency guidance (SR 26-2 / OCC 2026-13)
    # treats this entry as a model. Every inventory entry follows MRM-POL-001 either way.
    supervisory_classification: Mapped[str] = mapped_column(String(48), default="Model under SR 26-2")
    classification_rationale: Mapped[str] = mapped_column(Text, default="")
    lifecycle_stage: Mapped[str] = mapped_column(String(40), index=True)
    implementation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_validation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_validation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(40), index=True)
    documentation_checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    documentation_reviewed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    documentation_status: Mapped[str] = mapped_column(String(20), index=True)
    limitations: Mapped[str] = mapped_column(Text, default="")
    monitoring_frequency: Mapped[str] = mapped_column(String(20), default="Monthly")
    is_monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    archived_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    business_owner: Mapped[User] = relationship(foreign_keys=[business_owner_id], lazy="joined")
    model_risk_owner: Mapped[User] = relationship(foreign_keys=[model_risk_owner_id], lazy="joined")
    thresholds: Mapped[list["ModelThreshold"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="ModelThreshold.metric"
    )


class ModelThreshold(Base):
    """Configurable KPI / KRI limits per model and metric."""

    __tablename__ = "model_thresholds"
    __table_args__ = (UniqueConstraint("model_id", "metric", name="uq_threshold_model_metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(8), default="KPI")  # KPI or KRI
    direction: Mapped[str] = mapped_column(String(4))  # min or max
    warning_limit: Mapped[float] = mapped_column(Float)
    breach_limit: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    model: Mapped[InventoryModel] = relationship(back_populates="thresholds")
