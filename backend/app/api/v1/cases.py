from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import (
    CaseForUser,
    CurrentUser,
    DbSession,
    case_access_filter,
    require_role,
)
from app.models.case import Case, CaseEvent
from app.models.enums import CaseStatus, UserRole
from app.models.user import User
from app.schemas.case import (
    CaseAssign,
    CaseCreate,
    CaseEventOut,
    CaseOut,
    CasePage,
    CaseStatusUpdate,
    PageMeta,
)
from app.services import cases as case_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: DbSession,
    patient: Annotated[User, Depends(require_role(UserRole.PATIENT))],
) -> Case:
    return case_service.create_case(
        db,
        patient=patient,
        procedure_code=payload.procedure_code,
        target_countries=payload.target_countries,
    )


@router.get("", response_model=CasePage)
def list_cases(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: Annotated[CaseStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CasePage:
    """List cases visible to the caller.

    Scoping comes from the same ``case_access_filter`` the single-case dependency
    uses, so listing and fetching can never disagree.
    """
    total, items = case_service.count_and_list(
        db,
        access_filter=case_access_filter(current_user),
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return CasePage(
        items=[CaseOut.model_validate(case) for case in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case: CaseForUser) -> Case:
    return case


@router.patch("/{case_id}/status", response_model=CaseOut)
def update_case_status(
    payload: CaseStatusUpdate,
    case: CaseForUser,
    current_user: CurrentUser,
    db: DbSession,
) -> Case:
    return case_service.change_status(
        db, case=case, actor=current_user, new_status=payload.status, reason=payload.reason
    )


@router.post("/{case_id}/assign", response_model=CaseOut)
def assign_case(
    payload: CaseAssign,
    case: CaseForUser,
    db: DbSession,
    actor: Annotated[User, Depends(require_role(UserRole.COORDINATOR, UserRole.ADMIN))],
) -> Case:
    return case_service.assign_coordinator(
        db, case=case, actor=actor, coordinator_id=payload.coordinator_id
    )


@router.get("/{case_id}/events", response_model=list[CaseEventOut])
def list_case_events(case: CaseForUser, db: DbSession) -> list[CaseEvent]:
    return list(
        db.scalars(
            select(CaseEvent)
            .where(CaseEvent.case_id == case.id)
            .order_by(CaseEvent.created_at.asc())
        )
    )
