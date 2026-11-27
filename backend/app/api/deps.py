"""Request dependencies: database session, authenticated user, permission checks."""
from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.permissions import has_permission
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.users import User

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token expired") from None
    except jwt.PyJWTError:
        raise Unauthorized("Invalid token") from None
    user = db.execute(select(User).where(User.username == payload.get("sub"))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise Unauthorized("User not found or inactive")
    return user


def require(permission: str) -> Callable[..., User]:
    def checker(user: User = Depends(current_user)) -> User:
        if not has_permission(user.role, permission):
            raise Forbidden(f"Role '{user.role}' lacks permission '{permission}'")
        return user

    checker.__name__ = f"require_{permission.replace(':', '_')}"
    return checker


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
