from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import CaseEventType, CaseStatus


def normalize_country_codes(values: list[str] | None) -> list[str] | None:
    """Upper-case, validate as ISO 3166-1 alpha-2, and drop duplicates (order-preserving)."""
    if values is None:
        return None
    normalized: list[str] = []
    for value in values:
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError(f"{value!r} is not an ISO 3166-1 alpha-2 country code")
        if code not in normalized:
            normalized.append(code)
    return normalized


class CaseCreate(BaseModel):
    procedure_code: str = Field(min_length=1, max_length=32)
    target_countries: list[str] = Field(default_factory=list, max_length=20)

    _normalize = field_validator("target_countries")(normalize_country_codes)


class CaseUpdate(BaseModel):
    procedure_code: str | None = Field(default=None, min_length=1, max_length=32)
    target_countries: list[str] | None = Field(default=None, max_length=20)

    _normalize = field_validator("target_countries")(normalize_country_codes)


class CaseStatusUpdate(BaseModel):
    status: CaseStatus
    reason: str | None = Field(default=None, max_length=500)


class CaseAssign(BaseModel):
    """Omit ``coordinator_id`` to claim the case for yourself."""

    coordinator_id: uuid.UUID | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    coordinator_id: uuid.UUID | None
    procedure_code: str
    status: CaseStatus
    target_countries: list[str]
    created_at: datetime
    updated_at: datetime


class CaseEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: CaseEventType
    payload: dict[str, Any]
    created_at: datetime


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class CasePage(BaseModel):
    items: list[CaseOut]
    meta: PageMeta
