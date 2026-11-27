from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"
    __table_args__ = (Index("ix_run_model_period", "model_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    reference_start: Mapped[str] = mapped_column(String(7))
    reference_end: Mapped[str] = mapped_column(String(7))
    record_count: Mapped[int] = mapped_column(Integer)
    reference_count: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(16), default="baseline")
    triggered_by: Mapped[str] = mapped_column(String(64))
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    run_at: Mapped[datetime] = mapped_column(default=utcnow)
    overall_status: Mapped[str] = mapped_column(String(20))

    metrics: Mapped[list["MetricResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    drift: Mapped[list["FeatureDrift"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class MetricResult(Base):
    __tablename__ = "metric_results"
    __table_args__ = (Index("ix_metric_model_metric", "model_id", "metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    period: Mapped[str] = mapped_column(String(7))
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    numerator: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    denominator: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    warning_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    breach_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[MonitoringRun] = relationship(back_populates="metrics")


class FeatureDrift(Base):
    __tablename__ = "feature_drift"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(48))
    feature_type: Mapped[str] = mapped_column(String(12))  # numeric or categorical
    psi: Mapped[float] = mapped_column(Float)
    test_name: Mapped[str] = mapped_column(String(24))
    statistic: Mapped[float] = mapped_column(Float)
    p_value: Mapped[float] = mapped_column(Float)
    effect_size: Mapped[float] = mapped_column(Float)
    drift_flag: Mapped[bool] = mapped_column(Boolean)
    drift_level: Mapped[str] = mapped_column(String(16))
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[MonitoringRun] = relationship(back_populates="drift")


class Breach(Base):
    __tablename__ = "breaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    breach_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    warning_limit: Mapped[float] = mapped_column(Float)
    breach_limit: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(4))
    level: Mapped[str] = mapped_column(String(10))  # Warning or Breach
    severity: Mapped[str] = mapped_column(String(10), index=True)
    consecutive_periods: Mapped[int] = mapped_column(Integer, default=1)
    severity_rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="Open", index=True)
    detected_at: Mapped[datetime] = mapped_column(default=utcnow)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
