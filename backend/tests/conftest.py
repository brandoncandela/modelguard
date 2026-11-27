"""Shared fixtures. One seeded SQLite template per test session; each test module gets its own copy."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="modelguard-tests-"))
TEMPLATE = TMP / "template.db"
TEST_PASSWORD = "test-only-password-1"

os.environ.update({
    "MODELGUARD_ENV": "test",
    "MODELGUARD_SECRET_KEY": "test-secret-key-for-pytest-only-0123456789",
    "MODELGUARD_DEMO_PASSWORD": TEST_PASSWORD,
    "MODELGUARD_DATABASE_URL": f"sqlite:///{TEMPLATE}",
    "MODELGUARD_DATA_DIR": str(TMP / "var"),
    "MODELGUARD_AS_OF_DATE": "2026-11-25",
    "MODELGUARD_ANCHOR_DATE": "2026-10-31",
    "MODELGUARD_LOG_LEVEL": "WARNING",
})

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine, reset_engine  # noqa: E402


def _use_db(url: str) -> None:
    os.environ["MODELGUARD_DATABASE_URL"] = url
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(scope="session")
def template_db():
    if os.environ.get("MODELGUARD_TEST_DATABASE_URL"):
        # Run the suite against another database (for example PostgreSQL): seeded once, shared
        url = os.environ["MODELGUARD_TEST_DATABASE_URL"]
        _use_db(url)
        from app.seed.run import seed_database

        seed_database(get_engine(), get_settings(), password=TEST_PASSWORD)
        return url
    _use_db(f"sqlite:///{TEMPLATE}")
    from app.seed.run import seed_database

    seed_database(get_engine(), get_settings(), password=TEST_PASSWORD)
    reset_engine()
    return str(TEMPLATE)


@pytest.fixture(scope="module")
def db_url(template_db, request):
    if os.environ.get("MODELGUARD_TEST_DATABASE_URL"):
        from app.seed.run import seed_database

        _use_db(os.environ["MODELGUARD_TEST_DATABASE_URL"])
        if request.module.__name__ not in ("test_simulation", "test_analytics"):
            seed_database(get_engine(), get_settings(), password=TEST_PASSWORD)
        yield os.environ["MODELGUARD_TEST_DATABASE_URL"]
        return
    name = request.module.__name__.replace(".", "_")
    path = TMP / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(TEMPLATE) + suffix)
        if src.exists():
            shutil.copy(src, str(path) + suffix)
    url = f"sqlite:///{path}"
    _use_db(url)
    yield url
    reset_engine()


@pytest.fixture(scope="module")
def db(db_url):
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client(db_url):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    cache = {}

    def headers(username: str):
        if username not in cache:
            r = client.post("/api/v1/auth/login", json={"username": username, "password": TEST_PASSWORD})
            assert r.status_code == 200, r.text
            cache[username] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[username]

    return headers
