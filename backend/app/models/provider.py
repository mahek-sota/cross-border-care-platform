from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)

    specialties: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    accreditations: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'::varchar[]")
    )

    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    bed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intl_patient_services: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    established_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Maintained by the ``providers_search_vector_update`` trigger (see migration 0001).
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)

    procedures: Mapped[list[ProcedurePrice]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "avg_rating IS NULL OR (avg_rating >= 0 AND avg_rating <= 5)",
            name="ck_providers_avg_rating_range",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_providers_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_providers_longitude_range",
        ),
        Index("ix_providers_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_providers_specialties", "specialties", postgresql_using="gin"),
        Index("ix_providers_languages", "languages", postgresql_using="gin"),
        Index(
            "ix_providers_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Provider {self.name} ({self.city}, {self.country})>"


class ProcedurePrice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "procedure_prices"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    procedure_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    procedure_name: Mapped[str] = mapped_column(String(200), nullable=False)
    price_min_usd: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    price_max_usd: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    typical_stay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wait_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    provider: Mapped[Provider] = relationship(back_populates="procedures")

    __table_args__ = (
        UniqueConstraint("provider_id", "procedure_code", name="uq_procedure_prices_provider_code"),
        CheckConstraint("price_min_usd >= 0", name="ck_procedure_prices_min_non_negative"),
        CheckConstraint(
            "price_max_usd >= price_min_usd", name="ck_procedure_prices_max_gte_min"
        ),
    )
