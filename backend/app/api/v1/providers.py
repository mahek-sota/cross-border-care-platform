from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession
from app.schemas.case import PageMeta
from app.schemas.provider import (
    ProcedurePriceOut,
    ProviderComparison,
    ProviderDetail,
    ProviderFacets,
    ProviderPage,
    ProviderSearchQuery,
    ProviderSort,
    ProviderSummary,
)
from app.services import providers as provider_service

router = APIRouter(prefix="/providers", tags=["providers"])

MAX_COMPARE = 4


@router.get("", response_model=ProviderPage)
def search_providers(
    current_user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200, description="Free-text search")] = None,
    country: Annotated[list[str] | None, Query()] = None,
    specialty: Annotated[list[str] | None, Query()] = None,
    language: Annotated[list[str] | None, Query()] = None,
    accreditation: Annotated[list[str] | None, Query()] = None,
    procedure_code: Annotated[str | None, Query(max_length=32)] = None,
    max_price_usd: Annotated[Decimal | None, Query(ge=0)] = None,
    min_rating: Annotated[Decimal | None, Query(ge=0, le=5)] = None,
    intl_patient_services: Annotated[bool | None, Query()] = None,
    sort: Annotated[ProviderSort, Query()] = ProviderSort.RELEVANCE,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProviderPage:
    """Search providers by text, location, specialty, procedure, price, and rating.

    Providers are reference data: any signed-in user may browse them. Nothing here is
    patient-specific, so no object-level scoping applies.
    """
    try:
        query = ProviderSearchQuery(
            q=q,
            country=country,
            specialty=specialty,
            language=language,
            accreditation=accreditation,
            procedure_code=procedure_code,
            max_price_usd=max_price_usd,
            min_rating=min_rating,
            intl_patient_services=intl_patient_services,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ValidationError as exc:
        # The model normalises country codes, so its errors are bad *input*, not a
        # server fault. Re-raise as the 422 FastAPI would have produced itself.
        raise RequestValidationError(exc.errors()) from exc
    total, rows = provider_service.search_providers(db, query)

    items = []
    for provider, matched_price in rows:
        summary = ProviderSummary.model_validate(provider)
        if matched_price is not None:
            summary.matched_procedure = ProcedurePriceOut.model_validate(matched_price)
        items.append(summary)

    return ProviderPage(
        items=items, meta=PageMeta(total=total, limit=limit, offset=offset)
    )


@router.get("/facets", response_model=ProviderFacets)
def provider_facets(current_user: CurrentUser, db: DbSession) -> ProviderFacets:
    """Distinct filter values with counts, for building the filter controls."""
    return ProviderFacets.model_validate(provider_service.provider_facets(db))


@router.get("/compare", response_model=ProviderComparison)
def compare_providers(
    current_user: CurrentUser,
    db: DbSession,
    ids: Annotated[list[uuid.UUID], Query(min_length=2, max_length=MAX_COMPARE)],
    procedure_code: Annotated[str | None, Query(max_length=32)] = None,
) -> ProviderComparison:
    """Load 2-4 providers side by side, optionally narrowed to one procedure."""
    unique_ids = list(dict.fromkeys(ids))
    rows = provider_service.compare_providers(db, unique_ids, procedure_code)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No matching providers"
        )

    providers = []
    for provider, prices in rows:
        detail = ProviderDetail.model_validate(provider)
        detail.procedures = [ProcedurePriceOut.model_validate(price) for price in prices]
        providers.append(detail)

    return ProviderComparison(procedure_code=procedure_code, providers=providers)


@router.get("/{provider_id}", response_model=ProviderDetail)
def get_provider(
    provider_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> ProviderDetail:
    provider = provider_service.get_provider(db, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    detail = ProviderDetail.model_validate(provider)
    detail.procedures = [
        ProcedurePriceOut.model_validate(price)
        for price in sorted(provider.procedures, key=lambda price: price.procedure_code)
    ]
    return detail
