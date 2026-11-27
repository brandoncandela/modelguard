"""Synthetic operational data: customers, transactions, alerts and model scores."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    segment: Mapped[str] = mapped_column(String(32), index=True)
    country: Mapped[str] = mapped_column(String(2))
    nationality_region: Mapped[str] = mapped_column(String(32))
    industry: Mapped[str] = mapped_column(String(48))
    onboarding_date: Mapped[date] = mapped_column(Date)
    pep_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_monthly_volume: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_rating: Mapped[str] = mapped_column(String(10), index=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)  # synthetic ground truth
    typology: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_txn_period_customer", "period", "customer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_id: Mapped[str] = mapped_column(String(20), index=True)
    customer_id: Mapped[str] = mapped_column(String(16), index=True)
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    channel: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))
    counterparty_name: Mapped[str] = mapped_column(String(120))
    counterparty_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)  # synthetic ground truth
    typology: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    dq_issue: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    scenario: Mapped[str] = mapped_column(String(16), default="baseline")


class Application(Base):
    """Onboarding applications scored by the onboarding and screening models."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    applicant_name: Mapped[str] = mapped_column(String(120))
    related_parties: Mapped[list] = mapped_column(JSON, default=list)
    segment: Mapped[str] = mapped_column(String(32))
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    nationality_region: Mapped[str] = mapped_column(String(32))
    industry: Mapped[str] = mapped_column(String(48))
    ownership_layers: Mapped[int] = mapped_column(Integer)
    expected_monthly_volume: Mapped[float] = mapped_column(Float)
    cash_intensive: Mapped[bool] = mapped_column(Boolean)
    source_of_funds_documented: Mapped[bool] = mapped_column(Boolean)
    is_high_risk: Mapped[bool] = mapped_column(Boolean)  # synthetic ground truth
    dq_issue: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    scenario: Mapped[str] = mapped_column(String(16), default="baseline")


class WatchlistEntry(Base):
    """Fictional sanctions, PEP and law-enforcement list entries."""

    __tablename__ = "watchlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[str] = mapped_column(String(16), unique=True)
    list_type: Mapped[str] = mapped_column(String(16), index=True)  # SANCTIONS, PEP, WATCHLIST
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))


class MediaArticle(Base):
    __tablename__ = "media_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    subject_name: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    is_relevant: Mapped[bool] = mapped_column(Boolean)  # synthetic ground truth
    scenario: Mapped[str] = mapped_column(String(16), default="baseline")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_model_period", "model_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    created_on: Mapped[date] = mapped_column(Date)
    subject_ref: Mapped[str] = mapped_column(String(40))
    customer_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    rule_hits: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8))
    disposition: Mapped[str] = mapped_column(String(40))
    escalated: Mapped[bool] = mapped_column(Boolean)
    sar_filed: Mapped[bool] = mapped_column(Boolean)
    is_productive: Mapped[bool] = mapped_column(Boolean)  # synthetic ground truth


class ScoredRecord(Base):
    """Every record a model scored in a period. Monitoring metrics are computed from these rows."""

    __tablename__ = "scored_records"
    __table_args__ = (Index("ix_scored_model_period", "model_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    period: Mapped[str] = mapped_column(String(7))
    record_ref: Mapped[str] = mapped_column(String(40))
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted: Mapped[bool] = mapped_column(Boolean)
    actual: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    escalated: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    segment: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    dq_issue: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    scenario: Mapped[str] = mapped_column(String(16), default="baseline")


class SimulationPeriod(Base):
    """Which synthetic periods exist and which drift scenario produced each one."""

    __tablename__ = "simulation_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True)
    period_index: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(16))
    drift_intensity: Mapped[float] = mapped_column(Float)
    is_reference: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(16), default="seed")  # seed or simulation
    notes: Mapped[str] = mapped_column(Text, default="")


class SystemSetting(Base):
    """Small key-value store, e.g. the synthetic world configuration used by the seed."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
