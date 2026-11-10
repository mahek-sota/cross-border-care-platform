"""Case lifecycle rules: who may move a case where, and the audit trail that follows.

NOTE: the transition table below is a first pass drawn from the status enum, pending
the full case-workflow spec. It is deliberately centralised here so tightening it later
is a one-file change.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.enums import CaseEventType, CaseStatus, UserRole
from app.models.user import User
from app.services.case_events import record_event

# Which statuses may follow a given status, regardless of who asks.
ALLOWED_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.DRAFT: frozenset({CaseStatus.SUBMITTED, CaseStatus.CANCELLED}),
    CaseStatus.SUBMITTED: frozenset({CaseStatus.UNDER_REVIEW, CaseStatus.CANCELLED}),
    CaseStatus.UNDER_REVIEW: frozenset({CaseStatus.PROVIDER_MATCHED, CaseStatus.CANCELLED}),
    CaseStatus.PROVIDER_MATCHED: frozenset({CaseStatus.QUOTED, CaseStatus.CANCELLED}),
    CaseStatus.QUOTED: frozenset({CaseStatus.SCHEDULED, CaseStatus.CANCELLED}),
    CaseStatus.SCHEDULED: frozenset({CaseStatus.COMPLETED, CaseStatus.CANCELLED}),
    CaseStatus.COMPLETED: frozenset(),
    CaseStatus.CANCELLED: frozenset(),
}

# Transitions a patient may perform on their own case. Everything else is staff-driven.
PATIENT_TRANSITIONS: frozenset[CaseStatus] = frozenset({CaseStatus.SUBMITTED, CaseStatus.CANCELLED})


def create_case(
    db: Session, *, patient: User, procedure_code: str, target_countries: list[str]
) -> Case:
    case = Case(
        patient_id=patient.id,
        procedure_code=procedure_code,
        target_countries=target_countries,
        status=CaseStatus.DRAFT,
    )
    db.add(case)
    db.flush()
    record_event(
        db,
        case=case,
        actor_id=patient.id,
        event_type=CaseEventType.CASE_CREATED,
        payload={"procedure_code": procedure_code, "target_countries": target_countries},
    )
    db.commit()
    db.refresh(case)
    return case


def change_status(
    db: Session,
    *,
    case: Case,
    actor: User,
    new_status: CaseStatus,
    reason: str | None = None,
) -> Case:
    previous = case.status

    if new_status == previous:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Case is already {previous.value}",
        )
    if new_status not in ALLOWED_TRANSITIONS[previous]:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Cannot move a case from {previous.value} to {new_status.value}",
        )
    if actor.role is UserRole.PATIENT and new_status not in PATIENT_TRANSITIONS:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Patients may only submit or cancel their own case",
        )
    # A coordinator who can see an unassigned case in the queue still may not drive it
    # without claiming it first; otherwise two coordinators can race on one case.
    if (
        actor.role is UserRole.COORDINATOR
        and case.coordinator_id != actor.id
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Claim the case before changing its status",
        )

    case.status = new_status
    db.add(case)
    record_event(
        db,
        case=case,
        actor_id=actor.id,
        event_type=CaseEventType.STATUS_CHANGED,
        payload={"from": previous.value, "to": new_status.value, "reason": reason},
    )
    db.commit()
    db.refresh(case)
    return case


def assign_coordinator(
    db: Session, *, case: Case, actor: User, coordinator_id: uuid.UUID | None
) -> Case:
    """Claim a case (coordinator, self only) or assign one (admin, anybody)."""
    target_id = coordinator_id if coordinator_id is not None else actor.id

    if actor.role is UserRole.COORDINATOR and target_id != actor.id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Coordinators may only claim cases for themselves",
        )

    coordinator = db.get(User, target_id)
    if coordinator is None or coordinator.role is not UserRole.COORDINATOR:
        raise HTTPException(
            status_code=422,
            detail="Target user is not a coordinator",
        )
    if case.coordinator_id == target_id:
        return case
    if case.coordinator_id is not None and actor.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Case is already claimed by another coordinator",
        )

    previous_id = case.coordinator_id
    case.coordinator_id = target_id
    db.add(case)
    record_event(
        db,
        case=case,
        actor_id=actor.id,
        event_type=CaseEventType.COORDINATOR_ASSIGNED,
        payload={
            "from": str(previous_id) if previous_id else None,
            "to": str(target_id),
        },
    )
    db.commit()
    db.refresh(case)
    return case


def count_and_list(
    db: Session,
    *,
    access_filter,
    status_filter: CaseStatus | None,
    limit: int,
    offset: int,
) -> tuple[int, list[Case]]:
    conditions = [access_filter]
    if status_filter is not None:
        conditions.append(Case.status == status_filter)

    total = db.scalar(select(func.count()).select_from(Case).where(*conditions)) or 0
    items = list(
        db.scalars(
            select(Case)
            .where(*conditions)
            .order_by(Case.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return total, items
