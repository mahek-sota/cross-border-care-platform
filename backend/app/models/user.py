from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.case import Case

user_role_enum = SAEnum(
    UserRole,
    name="user_role",
    values_callable=lambda enum: [member.value for member in enum],
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(user_role_enum, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    profile: Mapped[PatientProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    cases: Mapped[list[Case]] = relationship(
        back_populates="patient", foreign_keys="Case.patient_id"
    )
    assigned_cases: Mapped[list[Case]] = relationship(
        back_populates="coordinator", foreign_keys="Case.coordinator_id"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} ({self.role})>"


class PatientProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    user: Mapped[User] = relationship(back_populates="profile")


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Server-side record of issued refresh tokens, so logout can revoke them.

    The ``id`` column is the JWT's ``jti``.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship()

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
