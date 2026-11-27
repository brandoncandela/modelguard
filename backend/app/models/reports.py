from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.users import User


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    report_type: Mapped[str] = mapped_column(String(16))  # executive, mrmc, fcmoc, aigc, validation
    title: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column(Date)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)
    file_name: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(200))

    generated_by: Mapped[User] = relationship(lazy="joined")
