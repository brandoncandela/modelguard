from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Column, Date, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.inventory import InventoryModel
from app.models.users import User

control_requirements = Table(
    "control_requirements",
    Base.metadata,
    Column("control_id", ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True),
    Column("requirement_id", ForeignKey("regulatory_requirements.id", ondelete="CASCADE"), primary_key=True),
)

control_models = Table(
    "control_models",
    Base.metadata,
    Column("control_id", ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True),
    Column("model_id", ForeignKey("models.id", ondelete="CASCADE"), primary_key=True),
)


class RegulatorySource(Base):
    __tablename__ = "regulatory_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    short_name: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(32))
    citation: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(300), default="")
    published_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_reviewed_on: Mapped[date] = mapped_column(Date)
    applicability: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="Current")  # Current, In force, Superseded, Rescinded
    superseded_by: Mapped[str] = mapped_column(String(160), default="")
    superseded_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    requirements: Mapped[list["RegulatoryRequirement"]] = relationship(
        back_populates="source", order_by="RegulatoryRequirement.requirement_id"
    )


class RegulatoryRequirement(Base):
    __tablename__ = "regulatory_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("regulatory_sources.id"), index=True)
    section: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    obligation_type: Mapped[str] = mapped_column(String(32))  # mirrors source type
    theme: Mapped[str] = mapped_column(String(48))

    source: Mapped[RegulatorySource] = relationship(back_populates="requirements", lazy="joined")
    controls: Mapped[list["Control"]] = relationship(secondary=control_requirements, back_populates="requirements")


class Control(Base):
    __tablename__ = "controls"

    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    control_type: Mapped[str] = mapped_column(String(32))  # Preventive, Detective, Governance
    frequency: Mapped[str] = mapped_column(String(32))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    evidence_requirement: Mapped[str] = mapped_column(Text)
    implementation_status: Mapped[str] = mapped_column(String(32), index=True)
    last_reviewed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_review_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    identified_gaps: Mapped[str] = mapped_column(Text, default="")
    remediation_actions: Mapped[str] = mapped_column(Text, default="")
    automated_test: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    documentation_refs: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(lazy="joined")
    requirements: Mapped[list[RegulatoryRequirement]] = relationship(
        secondary=control_requirements, back_populates="controls"
    )
    models: Mapped[list[InventoryModel]] = relationship(secondary=control_models)
    test_results: Mapped[list["ControlTestResult"]] = relationship(
        back_populates="control", cascade="all, delete-orphan", order_by="ControlTestResult.run_at.desc()"
    )


class ControlTestResult(Base):
    __tablename__ = "control_test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    test_name: Mapped[str] = mapped_column(String(48))
    result: Mapped[str] = mapped_column(String(16))  # Pass, Fail
    population: Mapped[int] = mapped_column(Integer)
    exceptions: Mapped[int] = mapped_column(Integer)
    exception_items: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    run_by: Mapped[str] = mapped_column(String(64))
    run_at: Mapped[datetime] = mapped_column(default=utcnow)

    control: Mapped[Control] = relationship(back_populates="test_results")
