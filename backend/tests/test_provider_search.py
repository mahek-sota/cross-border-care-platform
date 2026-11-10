"""Provider search, comparison, and facets."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.provider import ProcedurePrice, Provider

# name, country, city, specialties, accreditations, languages, rating, procedures
FIXTURES = [
    (
        "Bumrungrad International Hospital",
        "TH",
        "Bangkok",
        ["orthopedics", "cardiology"],
        ["JCI"],
        ["en", "th"],
        Decimal("4.60"),
        [("TKR-001", "Total knee replacement", 12000, 17000)],
    ),
    (
        "Apollo Hospitals Chennai",
        "IN",
        "Chennai",
        ["orthopedics", "transplant"],
        ["JCI", "NABH"],
        ["en", "hi"],
        Decimal("4.40"),
        [("TKR-001", "Total knee replacement", 6500, 9500)],
    ),
    (
        "Acibadem Maslak Hospital",
        "TR",
        "Istanbul",
        ["oncology", "neurosurgery"],
        ["JCI"],
        ["en", "tr"],
        Decimal("4.50"),
        [("SPINE-001", "Lumbar spinal fusion", 14000, 19000)],
    ),
    (
        "Clinica Santa Maria",
        "MX",
        "Tijuana",
        ["bariatrics"],
        [],
        ["es"],
        None,
        [("BARI-001", "Gastric sleeve", 5500, 8000)],
    ),
]


@pytest.fixture
def providers(db) -> dict[str, Provider]:
    created: dict[str, Provider] = {}
    for name, country, city, specialties, accreditations, languages, rating, procs in FIXTURES:
        provider = Provider(
            name=name,
            country=country,
            city=city,
            specialties=specialties,
            accreditations=accreditations,
            languages=languages,
            avg_rating=rating,
            intl_patient_services=country != "MX",
        )
        db.add(provider)
        db.flush()
        for code, proc_name, low, high in procs:
            db.add(
                ProcedurePrice(
                    provider_id=provider.id,
                    procedure_code=code,
                    procedure_name=proc_name,
                    price_min_usd=Decimal(low),
                    price_max_usd=Decimal(high),
                    typical_stay_days=7,
                    wait_time_days=10,
                )
            )
        created[name] = provider
    db.commit()
    return created


def names(payload: dict) -> list[str]:
    return [item["name"] for item in payload["items"]]


def search(client, headers, **params) -> dict:
    response = client.get("/api/v1/providers", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #


def test_search_requires_authentication(client, providers) -> None:
    assert client.get("/api/v1/providers").status_code == 401


def test_any_role_may_browse_providers(
    client, auth_headers, providers, patient, coordinator, admin
) -> None:
    """Providers are reference data, not patient-scoped."""
    for user in (patient, coordinator, admin):
        body = search(client, auth_headers(user))
        assert body["meta"]["total"] == len(FIXTURES)


# --------------------------------------------------------------------------- #
# Full-text search
# --------------------------------------------------------------------------- #


def test_full_text_search_matches_a_specialty(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), q="orthopedics")
    assert set(names(body)) == {
        "Bumrungrad International Hospital",
        "Apollo Hospitals Chennai",
    }


def test_full_text_search_stems(client, auth_headers, patient, providers) -> None:
    """'oncology' and 'oncological' share a stem, so either finds Acibadem."""
    body = search(client, auth_headers(patient), q="oncological")
    assert "Acibadem Maslak Hospital" in names(body)


def test_search_matches_city(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), q="Chennai")
    assert names(body) == ["Apollo Hospitals Chennai"]


def test_trigram_search_survives_a_typo(client, auth_headers, patient, providers) -> None:
    """Full-text alone cannot match a misspelling; pg_trgm similarity can."""
    body = search(client, auth_headers(patient), q="bumrangrad")
    assert "Bumrungrad International Hospital" in names(body)


def test_search_with_punctuation_does_not_error(
    client, auth_headers, patient, providers
) -> None:
    """websearch_to_tsquery must swallow input that would break to_tsquery."""
    for query in ["ortho & ! :*", "'unbalanced", "a | | b", "<->"]:
        response = client.get(
            "/api/v1/providers", params={"q": query}, headers=auth_headers(patient)
        )
        assert response.status_code == 200, f"{query!r} -> {response.text}"


def test_search_ranks_name_matches_above_weaker_ones(
    client, auth_headers, patient, providers
) -> None:
    body = search(client, auth_headers(patient), q="Apollo")
    assert names(body)[0] == "Apollo Hospitals Chennai"


def test_search_with_no_matches_is_an_empty_page(
    client, auth_headers, patient, providers
) -> None:
    body = search(client, auth_headers(patient), q="dermatology cruise ship")
    assert body["items"] == []
    assert body["meta"]["total"] == 0


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def test_filter_by_country(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), country=["IN", "TR"])
    assert set(names(body)) == {"Apollo Hospitals Chennai", "Acibadem Maslak Hospital"}


def test_country_filter_is_case_insensitive(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), country=["in"])
    assert names(body) == ["Apollo Hospitals Chennai"]


def test_invalid_country_code_is_rejected(client, auth_headers, patient, providers) -> None:
    response = client.get(
        "/api/v1/providers", params={"country": ["India"]}, headers=auth_headers(patient)
    )
    assert response.status_code == 422


def test_filter_by_specialty_uses_array_overlap(
    client, auth_headers, patient, providers
) -> None:
    body = search(client, auth_headers(patient), specialty=["transplant", "bariatrics"])
    assert set(names(body)) == {"Apollo Hospitals Chennai", "Clinica Santa Maria"}


def test_filter_by_language(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), language=["es"])
    assert names(body) == ["Clinica Santa Maria"]


def test_filter_by_accreditation(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), accreditation=["NABH"])
    assert names(body) == ["Apollo Hospitals Chennai"]


def test_filter_by_min_rating_excludes_unrated(
    client, auth_headers, patient, providers
) -> None:
    """A NULL rating is unknown, not zero, so it must not pass a rating floor."""
    body = search(client, auth_headers(patient), min_rating=4.5)
    assert set(names(body)) == {
        "Bumrungrad International Hospital",
        "Acibadem Maslak Hospital",
    }


def test_filter_by_intl_patient_services(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), intl_patient_services=False)
    assert names(body) == ["Clinica Santa Maria"]


def test_filters_combine_as_and(client, auth_headers, patient, providers) -> None:
    body = search(
        client, auth_headers(patient), q="orthopedics", country=["IN"], accreditation=["JCI"]
    )
    assert names(body) == ["Apollo Hospitals Chennai"]


# --------------------------------------------------------------------------- #
# Procedure + price
# --------------------------------------------------------------------------- #


def test_procedure_filter_restricts_and_attaches_the_price(
    client, auth_headers, patient, providers
) -> None:
    body = search(client, auth_headers(patient), procedure_code="TKR-001")
    assert set(names(body)) == {
        "Bumrungrad International Hospital",
        "Apollo Hospitals Chennai",
    }
    for item in body["items"]:
        assert item["matched_procedure"]["procedure_code"] == "TKR-001"


def test_no_procedure_filter_means_no_attached_price(
    client, auth_headers, patient, providers
) -> None:
    body = search(client, auth_headers(patient))
    assert all(item["matched_procedure"] is None for item in body["items"])


def test_max_price_with_a_procedure(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), procedure_code="TKR-001", max_price_usd=10000)
    assert names(body) == ["Apollo Hospitals Chennai"]


def test_max_price_without_a_procedure_matches_any(
    client, auth_headers, patient, providers
) -> None:
    """With no procedure chosen, a budget keeps providers offering anything under it."""
    body = search(client, auth_headers(patient), max_price_usd=6000)
    assert names(body) == ["Clinica Santa Maria"]


def test_sort_by_price_ascending(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), procedure_code="TKR-001", sort="price")
    assert names(body) == [
        "Apollo Hospitals Chennai",
        "Bumrungrad International Hospital",
    ]


def test_sort_by_rating_puts_unrated_last(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), sort="rating")
    assert names(body)[0] == "Bumrungrad International Hospital"
    assert names(body)[-1] == "Clinica Santa Maria"  # NULL rating


def test_sort_by_name(client, auth_headers, patient, providers) -> None:
    body = search(client, auth_headers(patient), sort="name")
    assert names(body) == sorted(names(body))


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #


def test_pagination_reports_full_total_and_does_not_repeat_rows(
    client, auth_headers, patient, providers
) -> None:
    first = search(client, auth_headers(patient), sort="name", limit=2, offset=0)
    second = search(client, auth_headers(patient), sort="name", limit=2, offset=2)

    assert first["meta"]["total"] == len(FIXTURES)
    assert second["meta"]["total"] == len(FIXTURES)
    assert len(first["items"]) == 2
    assert set(names(first)).isdisjoint(names(second))


def test_pagination_total_counts_providers_not_price_rows(
    client, auth_headers, patient, providers, db
) -> None:
    """A provider offering the procedure twice must still count once."""
    apollo = db.scalars(
        select(Provider).where(Provider.name == "Apollo Hospitals Chennai")
    ).one()
    db.add(
        ProcedurePrice(
            provider_id=apollo.id,
            procedure_code="HIP-001",
            procedure_name="Total hip replacement",
            price_min_usd=Decimal(7000),
            price_max_usd=Decimal(10500),
        )
    )
    db.commit()

    body = search(client, auth_headers(patient), max_price_usd=20000)
    assert body["meta"]["total"] == len(set(names(body)))


# --------------------------------------------------------------------------- #
# Detail
# --------------------------------------------------------------------------- #


def test_provider_detail_lists_every_procedure(
    client, auth_headers, patient, providers
) -> None:
    provider_id = providers["Bumrungrad International Hospital"].id
    response = client.get(f"/api/v1/providers/{provider_id}", headers=auth_headers(patient))
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Bumrungrad International Hospital"
    assert [p["procedure_code"] for p in body["procedures"]] == ["TKR-001"]


def test_unknown_provider_is_404(client, auth_headers, patient, providers) -> None:
    import uuid

    response = client.get(f"/api/v1/providers/{uuid.uuid4()}", headers=auth_headers(patient))
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Compare
# --------------------------------------------------------------------------- #


def test_compare_preserves_the_requested_order(
    client, auth_headers, patient, providers
) -> None:
    ids = [
        str(providers["Apollo Hospitals Chennai"].id),
        str(providers["Bumrungrad International Hospital"].id),
    ]
    response = client.get(
        "/api/v1/providers/compare", params={"ids": ids}, headers=auth_headers(patient)
    )
    assert response.status_code == 200
    body = response.json()
    assert [p["name"] for p in body["providers"]] == [
        "Apollo Hospitals Chennai",
        "Bumrungrad International Hospital",
    ]


def test_compare_narrowed_to_one_procedure(client, auth_headers, patient, providers) -> None:
    ids = [
        str(providers["Apollo Hospitals Chennai"].id),
        str(providers["Bumrungrad International Hospital"].id),
    ]
    response = client.get(
        "/api/v1/providers/compare",
        params={"ids": ids, "procedure_code": "TKR-001"},
        headers=auth_headers(patient),
    )
    body = response.json()
    assert body["procedure_code"] == "TKR-001"
    for provider in body["providers"]:
        assert [p["procedure_code"] for p in provider["procedures"]] == ["TKR-001"]


def test_compare_does_not_delete_the_filtered_out_prices(
    client, auth_headers, patient, providers, db
) -> None:
    """Regression: narrowing the comparison must not orphan other ProcedurePrice rows.

    ``Provider.procedures`` is delete-orphan, so assigning a filtered list to it would
    delete the excluded rows on the next flush.
    """
    apollo = providers["Apollo Hospitals Chennai"]
    db.add(
        ProcedurePrice(
            provider_id=apollo.id,
            procedure_code="HIP-001",
            procedure_name="Total hip replacement",
            price_min_usd=Decimal(7000),
            price_max_usd=Decimal(10500),
        )
    )
    db.commit()

    before = db.scalar(
        select(ProcedurePrice)
        .where(ProcedurePrice.provider_id == apollo.id)
        .with_only_columns(ProcedurePrice.id)
        .order_by(ProcedurePrice.procedure_code)
    )
    assert before is not None

    ids = [str(apollo.id), str(providers["Bumrungrad International Hospital"].id)]
    client.get(
        "/api/v1/providers/compare",
        params={"ids": ids, "procedure_code": "TKR-001"},
        headers=auth_headers(patient),
    )

    remaining = db.scalars(
        select(ProcedurePrice.procedure_code).where(ProcedurePrice.provider_id == apollo.id)
    ).all()
    assert set(remaining) == {"TKR-001", "HIP-001"}


def test_compare_requires_at_least_two_providers(
    client, auth_headers, patient, providers
) -> None:
    response = client.get(
        "/api/v1/providers/compare",
        params={"ids": [str(providers["Apollo Hospitals Chennai"].id)]},
        headers=auth_headers(patient),
    )
    assert response.status_code == 422


def test_compare_rejects_more_than_four(client, auth_headers, patient, providers, db) -> None:
    import uuid

    ids = [str(uuid.uuid4()) for _ in range(5)]
    response = client.get(
        "/api/v1/providers/compare", params={"ids": ids}, headers=auth_headers(patient)
    )
    assert response.status_code == 422


def test_compare_with_only_unknown_ids_is_404(client, auth_headers, patient, providers) -> None:
    import uuid

    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    response = client.get(
        "/api/v1/providers/compare", params={"ids": ids}, headers=auth_headers(patient)
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Facets
# --------------------------------------------------------------------------- #


def test_facets_count_providers_per_value(client, auth_headers, patient, providers) -> None:
    response = client.get("/api/v1/providers/facets", headers=auth_headers(patient))
    assert response.status_code == 200
    body = response.json()

    countries = {item["value"]: item["count"] for item in body["countries"]}
    assert countries == {"TH": 1, "IN": 1, "TR": 1, "MX": 1}

    specialties = {item["value"]: item["count"] for item in body["specialties"]}
    assert specialties["orthopedics"] == 2

    procedures = {item["value"]: item["count"] for item in body["procedures"]}
    assert procedures["TKR-001"] == 2


def test_facets_are_ordered_by_count_descending(
    client, auth_headers, patient, providers
) -> None:
    body = client.get("/api/v1/providers/facets", headers=auth_headers(patient)).json()
    counts = [item["count"] for item in body["specialties"]]
    assert counts == sorted(counts, reverse=True)
