from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CaseEventType, CaseStatus

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.provider import Provider
    from app.models.user import User

case_status_enum = SAEnum(
    CaseStatus,
    name="case_status",
    values_callable=lambda enum: [member.value for member in enum],
)

case_event_type_enum = SAEnum(
    CaseEventType,
    name="case_event_type",
    values_callable=lambda enum: [member.value for member in enum],
)


class Case(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cases"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    procedure_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[CaseStatus] = mapped_column(
        case_status_enum, nullable=False, default=CaseStatus.DRAFT, server_default="draft"
    )
    target_countries: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    patient: Mapped[User] = relationship(back_populates="cases", foreign_keys=[patient_id])
    coordinator: Mapped[User | None] = relationship(
        back_populates="assigned_cases", foreign_keys=[coordinator_id]
    )
    case_providers: Mapped[list[CaseProvider]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    events: Mapped[list[CaseEvent]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseEvent.created_at",
    )

    __table_args__ = (
        Index("ix_cases_status_created_at", "status", "created_at"),
        # Supports the coordinator queue: unassigned cases ordered by age.
        Index(
            "ix_cases_unassigned_queue",
            "created_at",
            postgresql_where=text("coordinator_id IS NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Case {self.id} {self.procedure_code} ({self.status})>"


class CaseProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "case_providers"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shortlisted_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    quoted_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="case_providers")
    provider: Mapped[Provider] = relationship()

    __table_args__ = (
        UniqueConstraint("case_id", "provider_id", name="uq_case_providers_case_provider"),
    )


class CaseEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only audit trail. Rows are never updated or deleted in application code."""

    __tablename__ = "case_events"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[CaseEventType] = mapped_column(case_event_type_enum, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case: Mapped[Case] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()

    __table_args__ = (Index("ix_case_events_case_id_created_at", "case_id", "created_at"),)
