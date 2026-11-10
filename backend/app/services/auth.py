"""Registration, login, refresh-token rotation, and logout."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import PatientProfile, RefreshToken, User
from app.schemas.auth import PatientProfileIn, TokenPair

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)

INVALID_REFRESH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token",
    headers={"WWW-Authenticate": "Bearer"},
)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real bcrypt hash of a random value, for constant-time-ish failed logins."""
    return hash_password(secrets.token_urlsafe(32))


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole,
    profile: PatientProfileIn | None = None,
) -> User:
    user = User(
        email=_normalize_email(email),
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    if profile is not None:
        db.add(PatientProfile(user=user, **profile.model_dump()))

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from exc

    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.scalars(select(User).where(User.email == _normalize_email(email))).first()
    # Hash against a dummy value when the user is missing so that a bad email and a
    # bad password take comparable time.
    if user is None:
        verify_password(password, _dummy_hash())
        raise INVALID_CREDENTIALS
    if not verify_password(password, user.hashed_password):
        raise INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )
    return user


def issue_token_pair(db: Session, user: User) -> TokenPair:
    access_token, access_expires_at = create_access_token(user_id=user.id, role=user.role.value)
    refresh_token, jti, refresh_expires_at = create_refresh_token(user_id=user.id)

    db.add(RefreshToken(id=jti, user_id=user.id, expires_at=refresh_expires_at))
    db.commit()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=access_expires_at,
    )


def _load_active_refresh_record(db: Session, token: str) -> RefreshToken:
    try:
        payload = decode_token(token, expected_type="refresh")
    except TokenError as exc:
        raise INVALID_REFRESH from exc

    try:
        jti = uuid.UUID(payload["jti"])
    except (KeyError, ValueError) as exc:
        raise INVALID_REFRESH from exc

    record = db.get(RefreshToken, jti)
    if record is None or record.is_revoked:
        raise INVALID_REFRESH
    if record.expires_at <= datetime.now(UTC):
        raise INVALID_REFRESH
    return record


def rotate_refresh_token(db: Session, token: str) -> TokenPair:
    """Exchange a refresh token for a new pair, revoking the presented token.

    Rotation is unconditional: a refresh token is single-use, so a stolen token is
    only usable until the legitimate holder next refreshes.
    """
    record = _load_active_refresh_record(db, token)

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise INVALID_REFRESH

    record.revoked_at = datetime.now(UTC)
    db.add(record)
    return issue_token_pair(db, user)


def revoke_refresh_token(db: Session, token: str) -> None:
    """Logout. Idempotent: revoking an already-revoked or unknown token is a no-op."""
    try:
        payload = decode_token(token, expected_type="refresh")
        jti = uuid.UUID(payload["jti"])
    except (TokenError, KeyError, ValueError):
        return

    db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    """Revoke every outstanding refresh token for a user (logout everywhere)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
