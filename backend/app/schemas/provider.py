from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.case import PageMeta


class ProviderSort(StrEnum):
    RELEVANCE = "relevance"
    PRICE = "price"
    RATING = "rating"
    NAME = "name"


class ProcedurePriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    procedure_code: str
    procedure_name: str
    price_min_usd: Decimal
    price_max_usd: Decimal
    typical_stay_days: int | None
    wait_time_days: int | None


class ProviderSummary(BaseModel):
    """A provider as it appears in search results."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str
    city: str
    specialties: list[str]
    accreditations: list[str]
    languages: list[str]
    avg_rating: Decimal | None
    bed_count: int | None
    intl_patient_services: bool
    latitude: Decimal | None
    longitude: Decimal | None
    established_year: int | None

    # Present only when the search filtered by procedure_code: the price for that
    # procedure at this provider, so results can be ranked and compared on it.
    matched_procedure: ProcedurePriceOut | None = None


class ProviderDetail(ProviderSummary):
    procedures: list[ProcedurePriceOut] = Field(default_factory=list)


class ProviderPage(BaseModel):
    items: list[ProviderSummary]
    meta: PageMeta


class FacetValue(BaseModel):
    value: str
    count: int


class ProviderFacets(BaseModel):
    """Distinct filter values across all providers, for building filter controls."""

    countries: list[FacetValue]
    specialties: list[FacetValue]
    languages: list[FacetValue]
    accreditations: list[FacetValue]
    procedures: list[FacetValue]


class ProviderComparison(BaseModel):
    """Providers aligned for side-by-side comparison on one procedure."""

    procedure_code: str | None
    providers: list[ProviderDetail]


def _upper_codes(values: list[str] | None) -> list[str] | None:
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


class ProviderSearchQuery(BaseModel):
    """Validated search parameters. Built from the query string by the router."""

    q: str | None = Field(default=None, max_length=200)
    country: list[str] | None = None
    specialty: list[str] | None = None
    language: list[str] | None = None
    accreditation: list[str] | None = None
    procedure_code: str | None = Field(default=None, max_length=32)
    max_price_usd: Decimal | None = Field(default=None, ge=0)
    min_rating: Decimal | None = Field(default=None, ge=0, le=5)
    intl_patient_services: bool | None = None
    sort: ProviderSort = ProviderSort.RELEVANCE
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    _normalize_country = field_validator("country")(_upper_codes)
