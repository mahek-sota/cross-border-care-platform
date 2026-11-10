"""Shared FastAPI dependencies: authentication, role gates, and object-level access.

The visibility rule for cases lives in exactly one place -- :func:`case_access_filter`.
Both the single-case dependency (:func:`get_case_for_user`) and every list endpoint
build on that same clause, so a case can never be listable but not fetchable (or the
reverse). Endpoints must never hand-roll a ``patient_id == current_user.id`` check.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models.case import Case
from app.models.enums import UserRole
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise CREDENTIALS_EXCEPTION from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Dependency factory gating an endpoint on the caller's role.

    Usage::

        @router.post("/", dependencies=[Depends(require_role(UserRole.ADMIN))])

    or, when the endpoint also needs the user::

        user: Annotated[User, Depends(require_role(UserRole.COORDINATOR, UserRole.ADMIN))]
    """
    if not roles:
        raise ValueError("require_role() needs at least one role")
    allowed = frozenset(roles)

    def dependency(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return dependency


def case_access_filter(user: User) -> ColumnElement[bool]:
    """The single source of truth for which cases a user may see.

    - patient:     only their own cases
    - coordinator: cases assigned to them, plus unassigned cases (their intake queue)
    - admin:       everything
    """
    match user.role:
        case UserRole.ADMIN:
            return Case.id.is_not(None)
        case UserRole.COORDINATOR:
            return or_(Case.coordinator_id == user.id, Case.coordinator_id.is_(None))
        case UserRole.PATIENT:
            return Case.patient_id == user.id
        case _:  # pragma: no cover - guards a future role added without a rule
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Role has no case access rule"
            )


def get_case_for_user(
    case_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
    db: DbSession,
) -> Case:
    """Load a case the caller is allowed to see, or 404.

    Returns 404 rather than 403 for cases outside the caller's scope so the endpoint
    does not confirm that some other patient's case exists.
    """
    case = db.scalars(
        select(Case).where(Case.id == case_id, case_access_filter(current_user))
    ).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


CaseForUser = Annotated[Case, Depends(get_case_for_user)]
