from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    LogoutRequest,
    MeOut,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession) -> TokenPair:
    """Self-registration. Always creates a patient; role is not caller-controlled."""
    user = auth_service.create_user(
        db,
        email=payload.email,
        password=payload.password,
        role=UserRole.PATIENT,
        profile=payload.profile,
    )
    return auth_service.issue_token_pair(db, user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    return auth_service.issue_token_pair(db, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    return auth_service.rotate_refresh_token(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: DbSession) -> None:
    auth_service.revoke_refresh_token(db, payload.refresh_token)


@router.get("/me", response_model=MeOut)
def me(current_user: CurrentUser) -> User:
    return current_user


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin"],
)
def create_user(
    payload: CreateUserRequest,
    db: DbSession,
    _admin: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> User:
    """Provision a coordinator or admin account. Admin only."""
    return auth_service.create_user(
        db, email=payload.email, password=payload.password, role=payload.role
    )
