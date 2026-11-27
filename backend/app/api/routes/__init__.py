"""Router registration."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import ai, audit, auth, findings, inventory, monitoring, regulatory, reporting, validations

ROUTERS = [auth, inventory, monitoring, validations, findings, ai, regulatory, reporting, audit]


def register(app: FastAPI, prefix: str) -> None:
    for module in ROUTERS:
        app.include_router(module.router, prefix=prefix)
