"""Password hashing (bcrypt) and signed access tokens (JWT, HS256)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    if len(password.encode()) > 72:
        raise ValueError("Password longer than 72 bytes")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, role: str, minutes: Optional[int] = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes or s.access_token_minutes),
        "iss": "modelguard",
    }
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.secret_key, algorithms=[ALGORITHM], issuer="modelguard")
