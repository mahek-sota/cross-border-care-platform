"""Provider search, comparison, and facets.

Text search combines two Postgres features, because they fail in opposite ways:

* ``search_vector`` (tsvector, GIN) matches on meaning -- stemming and weighting mean
  "orthopedic surgery" finds a provider whose specialty is "orthopedics". It cannot
  cope with a misspelling.
* ``similarity(name, q)`` (pg_trgm, GIN) matches on spelling, so "bumrungrad" still
  finds "Bumrungrad International Hospital" when typed as "bumrangrad". It has no
  idea what the words mean.

A provider matches if either does, and the ranking score sums them with full-text
weighted higher, so a genuine term match outranks a lucky fuzzy one.

``websearch_to_tsquery`` (not ``to_tsquery``) parses the user's raw input: it accepts
quoted phrases and OR/- operators but, crucially, never raises a syntax error on
stray punctuation, so no input sanitising is needed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, desc, exists, func, nulls_last, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.provider import ProcedurePrice, Provider
from app.schemas.provider import ProviderSearchQuery, ProviderSort

# Below this trigram similarity a fuzzy "match" is noise rather than a near-miss.
TRIGRAM_THRESHOLD = 0.2

# A full-text hit is worth more than a fuzzy one; ts_rank_cd and similarity are both
# roughly 0..1 here, so the multiplier decides which wins a tie.
FULLTEXT_WEIGHT = 2.0


def _text_match_score(q: str) -> tuple[Any, Any]:
    """Return ``(match_condition, relevance_score)`` for a free-text query."""
    tsquery = func.websearch_to_tsquery("english", q)
    rank = func.ts_rank_cd(Provider.search_vector, tsquery)
    similarity = func.similarity(Provider.name, q)

    match = or_(
        Provider.search_vector.op("@@")(tsquery),
        similarity > TRIGRAM_THRESHOLD,
    )
    score = rank * FULLTEXT_WEIGHT + similarity
    return match, score


def _apply_filters(stmt: Select, query: ProviderSearchQuery) -> Select:
    if query.country:
        stmt = stmt.where(Provider.country.in_(query.country))
    # ``overlap`` is the && array operator: keep providers sharing at least one value.
    if query.specialty:
        stmt = stmt.where(Provider.specialties.overlap(query.specialty))
    if query.language:
        stmt = stmt.where(Provider.languages.overlap(query.language))
    if query.accreditation:
        stmt = stmt.where(Provider.accreditations.overlap(query.accreditation))
    if query.min_rating is not None:
        stmt = stmt.where(Provider.avg_rating >= query.min_rating)
    if query.intl_patient_services is not None:
        stmt = stmt.where(Provider.intl_patient_services.is_(query.intl_patient_services))
    return stmt


def _price_conditions(query: ProviderSearchQuery) -> list[Any]:
    """Conditions applied to the joined ProcedurePrice row."""
    conditions: list[Any] = []
    if query.procedure_code:
        conditions.append(ProcedurePrice.procedure_code == query.procedure_code)
    if query.max_price_usd is not None:
        # Match on the low end: a provider qualifies if the procedure *can* be had
        # at or below the budget, even when the top of its range exceeds it.
        conditions.append(ProcedurePrice.price_min_usd <= query.max_price_usd)
    return conditions


def search_providers(
    db: Session, query: ProviderSearchQuery
) -> tuple[int, list[tuple[Provider, ProcedurePrice | None]]]:
    """Return ``(total, [(provider, matched_price_or_None), ...])``."""
    price_conditions = _price_conditions(query)

    # Joining on the procedure both filters to providers offering it and gives us the
    # price to sort and display. Without a procedure_code there is no single price to
    # attach, so a price ceiling becomes an EXISTS over any procedure instead.
    joins_price = bool(query.procedure_code)

    columns: list[Any] = [Provider]
    if joins_price:
        columns.append(ProcedurePrice)

    stmt = select(*columns)
    count_stmt = select(func.count(func.distinct(Provider.id))).select_from(Provider)

    if joins_price:
        join_condition = and_(ProcedurePrice.provider_id == Provider.id, *price_conditions)
        stmt = stmt.join(ProcedurePrice, join_condition)
        count_stmt = count_stmt.join(ProcedurePrice, join_condition)
    elif price_conditions:
        price_exists = exists().where(
            and_(ProcedurePrice.provider_id == Provider.id, *price_conditions)
        )
        stmt = stmt.where(price_exists)
        count_stmt = count_stmt.where(price_exists)

    stmt = _apply_filters(stmt, query)
    count_stmt = _apply_filters(count_stmt, query)

    score = None
    if query.q:
        match, score = _text_match_score(query.q)
        stmt = stmt.where(match)
        count_stmt = count_stmt.where(match)

    stmt = stmt.order_by(*_ordering(query, score, joins_price))

    total = db.scalar(count_stmt) or 0
    rows = db.execute(stmt.limit(query.limit).offset(query.offset)).all()

    if joins_price:
        results = [(row[0], row[1]) for row in rows]
    else:
        results = [(row[0], None) for row in rows]
    return total, results


def _ordering(query: ProviderSearchQuery, score: Any, joins_price: bool) -> list[Any]:
    """Sort clauses. Always ends with id so paging cannot repeat or skip a row."""
    match query.sort:
        case ProviderSort.PRICE if joins_price:
            primary = [ProcedurePrice.price_min_usd.asc()]
        case ProviderSort.PRICE:
            # No procedure selected means no single price to sort on; fall back to
            # rating rather than silently returning an arbitrary order.
            primary = [nulls_last(desc(Provider.avg_rating))]
        case ProviderSort.RATING:
            primary = [nulls_last(desc(Provider.avg_rating))]
        case ProviderSort.NAME:
            primary = [Provider.name.asc()]
        case _:  # relevance
            primary = (
                [desc(score)] if score is not None else [nulls_last(desc(Provider.avg_rating))]
            )
    return [*primary, Provider.id.asc()]


def get_provider(db: Session, provider_id: uuid.UUID) -> Provider | None:
    return db.scalars(
        select(Provider)
        .where(Provider.id == provider_id)
        .options(selectinload(Provider.procedures))
    ).first()


def compare_providers(
    db: Session, provider_ids: list[uuid.UUID], procedure_code: str | None
) -> list[tuple[Provider, list[ProcedurePrice]]]:
    """Load providers for side-by-side comparison, in the order requested.

    Returns the prices to display *alongside* each provider rather than narrowing
    ``provider.procedures`` in place: that attribute is a delete-orphan relationship,
    so assigning a filtered list to it would mark the excluded ProcedurePrice rows as
    orphans and delete them on the next flush.
    """
    providers = list(
        db.scalars(
            select(Provider)
            .where(Provider.id.in_(provider_ids))
            .options(selectinload(Provider.procedures))
        )
    )
    by_id = {provider.id: provider for provider in providers}

    def prices_for(provider: Provider) -> list[ProcedurePrice]:
        if not procedure_code:
            return sorted(provider.procedures, key=lambda price: price.procedure_code)
        # Comparing on one procedure: show only that row, so the columns line up.
        return [
            price for price in provider.procedures if price.procedure_code == procedure_code
        ]

    # Preserve the caller's ordering; silently drop ids that do not exist.
    return [(by_id[pid], prices_for(by_id[pid])) for pid in provider_ids if pid in by_id]


def _array_facet(db: Session, column: Any) -> list[dict[str, Any]]:
    value = func.unnest(column).label("value")
    stmt = (
        select(value, func.count().label("count"))
        .select_from(Provider)
        .group_by(value)
        .order_by(desc("count"), value)
    )
    return [{"value": row.value, "count": row.count} for row in db.execute(stmt)]


def _scalar_facet(db: Session, column: Any) -> list[dict[str, Any]]:
    stmt = (
        select(column.label("value"), func.count().label("count"))
        .group_by(column)
        .order_by(desc("count"), column)
    )
    return [{"value": row.value, "count": row.count} for row in db.execute(stmt)]


def provider_facets(db: Session) -> dict[str, list[dict[str, Any]]]:
    procedures_stmt = (
        select(
            ProcedurePrice.procedure_code.label("value"),
            func.count(func.distinct(ProcedurePrice.provider_id)).label("count"),
        )
        .group_by(ProcedurePrice.procedure_code)
        .order_by(desc("count"), ProcedurePrice.procedure_code)
    )
    return {
        "countries": _scalar_facet(db, Provider.country),
        "specialties": _array_facet(db, Provider.specialties),
        "languages": _array_facet(db, Provider.languages),
        "accreditations": _array_facet(db, Provider.accreditations),
        "procedures": [
            {"value": row.value, "count": row.count} for row in db.execute(procedures_stmt)
        ],
    }


def price_range_for(provider: Provider, procedure_code: str) -> tuple[Decimal, Decimal] | None:
    for price in provider.procedures:
        if price.procedure_code == procedure_code:
            return price.price_min_usd, price.price_max_usd
    return None
