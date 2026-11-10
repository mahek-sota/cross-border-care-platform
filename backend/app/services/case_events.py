"""The only sanctioned way to append to the case audit trail.

Every status change, assignment, and document lifecycle event goes through
:func:`record_event`. It stages the row on the caller's session without committing,
so the event and the change it describes land in the same transaction -- an audit
trail that can disagree with the case row is worse than none.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.case import Case, CaseEvent
from app.models.enums import CaseEventType


def record_event(
    db: Session,
    *,
    case: Case | uuid.UUID,
    actor_id: uuid.UUID | None,
    event_type: CaseEventType,
    payload: dict[str, Any] | None = None,
) -> CaseEvent:
    case_id = case.id if isinstance(case, Case) else case
    event = CaseEvent(
        case_id=case_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload or {},
    )
    db.add(event)
    return event
