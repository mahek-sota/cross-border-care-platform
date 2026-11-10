"""Password hashing and JWT access/refresh token issuance.

Access tokens are stateless and short-lived. Refresh tokens carry a ``jti`` that is
recorded in the ``refresh_tokens`` table so logout (and rotation-on-refresh) can
actually revoke them -- a stateless refresh token cannot be withdrawn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import settings

TokenType = Literal["access", "refresh"]

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(Exception):
    """Raised when a token is malformed, expired, or of the wrong type."""


def hash_password(plain_password: str) -> str:
    # bcrypt silently truncates at 72 bytes; reject rather than hash a prefix.
    if len(plain_password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Malformed/unknown hash in the row -- treat as a failed login, not a 500.
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    issued_at = _now()
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    token = _encode(
        {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "iat": issued_at,
            "exp": expires_at,
            "jti": str(uuid.uuid4()),
        }
    )
    return token, expires_at


def create_refresh_token(*, user_id: uuid.UUID) -> tuple[str, uuid.UUID, datetime]:
    """Return ``(token, jti, expires_at)``; the caller persists the jti."""
    issued_at = _now()
    expires_at = issued_at + timedelta(days=settings.refresh_token_expire_days)
    jti = uuid.uuid4()
    token = _encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "iat": issued_at,
            "exp": expires_at,
            "jti": str(jti),
        }
    )
    return token, jti, expires_at


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")
    return payload
