"""Application settings, read from environment variables (and an optional .env file).

Nothing secret has a default. In production the app refuses to start without a
secret key; in development and test a random key is generated for the process.
"""
from __future__ import annotations

import logging
import secrets
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

log = logging.getLogger("modelguard.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODELGUARD_",
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field("development", pattern="^(development|test|production)$")
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'var' / 'modelguard.db').as_posix()}"
    secret_key: Optional[str] = None
    access_token_minutes: int = Field(60, ge=5, le=720)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    data_dir: str = str(BACKEND_DIR / "var")
    log_level: str = "INFO"

    # Login protection
    max_failed_logins: int = Field(5, ge=3, le=20)
    lockout_minutes: int = Field(15, ge=1, le=1440)

    # Synthetic data generation
    seed: int = 20261031
    anchor_date: Optional[date] = None  # last day of the latest complete period; defaults to today
    history_months: int = Field(12, ge=8, le=36)
    drift_scenario: str = Field("moderate", pattern="^(none|moderate|severe)$")
    drift_periods: int = Field(3, ge=0, le=12)
    demo_password: Optional[str] = None

    # Business date used for overdue calculations; defaults to today
    as_of_date: Optional[date] = None

    institution_name: str = "Candela Bank (fictional)"

    @field_validator("database_url")
    @classmethod
    def _normalise_postgres_driver(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def today(self) -> date:
        return self.as_of_date or date.today()


_EPHEMERAL_KEY = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key:
        if s.env == "production":
            raise RuntimeError("MODELGUARD_SECRET_KEY must be set in production")
        log.warning("MODELGUARD_SECRET_KEY not set; using a random key for this process only")
        s.secret_key = _EPHEMERAL_KEY
    elif len(s.secret_key) < 32:
        raise RuntimeError("MODELGUARD_SECRET_KEY must be at least 32 characters")
    return s
