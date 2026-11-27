from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, require
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.permissions import ROLE_LABELS, permissions_for
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.users import User
from app.schemas.common import UserRef
from app.services import audit

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Me(UserRef):
    email: str
    business_unit: str
    role_label: str
    permissions: List[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Me


def _me(u: User) -> Me:
    return Me(id=u.id, username=u.username, full_name=u.full_name, role=u.role, title=u.title, email=u.email,
              business_unit=u.business_unit, role_label=ROLE_LABELS.get(u.role, u.role),
              permissions=permissions_for(u.role))


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    now = datetime.now(timezone.utc)
    ip = client_ip(request)
    user = db.execute(select(User).where(User.username == body.username.strip().lower())).scalar_one_or_none()
    if user is not None and user.locked_until and _aware(user.locked_until) > now:
        audit.record(db, user.username, user.role, "LOGIN_BLOCKED", "user", user.username,
                     "Sign-in attempt while account locked", ip_address=ip)
        db.commit()
        raise Unauthorized("Account temporarily locked after repeated failed sign-ins")
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= s.max_failed_logins:
                user.locked_until = now + timedelta(minutes=s.lockout_minutes)
                audit.record(db, user.username, user.role, "ACCOUNT_LOCKED", "user", user.username,
                             f"Locked for {s.lockout_minutes} minutes after {user.failed_logins} failed sign-ins",
                             ip_address=ip)
            else:
                audit.record(db, user.username, user.role, "LOGIN_FAILED", "user", user.username,
                             "Incorrect password", ip_address=ip)
        else:
            audit.record(db, "anonymous", "none", "LOGIN_FAILED", "user", body.username[:48], "Unknown username",
                         ip_address=ip)
        db.commit()
        raise Unauthorized("Invalid username or password")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    audit.record(db, user.username, user.role, "LOGIN", "user", user.username, "Signed in", ip_address=ip)
    db.commit()
    token = create_access_token(user.username, user.role)
    return LoginResponse(access_token=token, expires_in=s.access_token_minutes * 60, user=_me(user))


@router.get("/auth/me", response_model=Me)
def me(user: User = Depends(current_user)):
    return _me(user)


@router.get("/users", response_model=List[UserRef], tags=["system"])
def users(role: str = None, db: Session = Depends(get_db), _: User = Depends(require("user:read"))):
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    if role:
        stmt = stmt.where(User.role == role)
    return list(db.execute(stmt).scalars())
