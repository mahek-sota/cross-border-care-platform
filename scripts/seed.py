#!/usr/bin/env python
"""Seed the database with demo users, providers, and a couple of cases.

    python scripts/seed.py            # add anything missing, leave the rest alone
    python scripts/seed.py --reset    # delete seeded rows first

Safe to re-run: every insert is keyed on a natural identifier and skipped if present.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.enums import CaseEventType, CaseStatus, UserRole  # noqa: E402
from app.models.provider import ProcedurePrice, Provider  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import create_user  # noqa: E402
from app.services.case_events import record_event  # noqa: E402
from app.schemas.auth import PatientProfileIn  # noqa: E402

DEMO_PASSWORD = "correct-horse-battery"

USERS = [
    ("patient@example.com", UserRole.PATIENT, "Ada Lovelace", "GB"),
    ("patient2@example.com", UserRole.PATIENT, "Grace Hopper", "US"),
    ("coordinator@example.com", UserRole.COORDINATOR, None, None),
    ("coordinator2@example.com", UserRole.COORDINATOR, None, None),
    ("admin@example.com", UserRole.ADMIN, None, None),
]

PROVIDERS = [
    {
        "name": "Bumrungrad International Hospital",
        "country": "TH",
        "city": "Bangkok",
        "specialties": ["orthopedics", "cardiology", "oncology"],
        "accreditations": ["JCI", "HA Thailand"],
        "languages": ["en", "th", "ar"],
        "avg_rating": Decimal("4.60"),
        "bed_count": 580,
        "intl_patient_services": True,
        "latitude": Decimal("13.746900"),
        "longitude": Decimal("100.552700"),
        "established_year": 1980,
        "procedures": [
            ("TKR-001", "Total knee replacement", 12000, 17000, 7, 14),
            ("CABG-001", "Coronary artery bypass graft", 24000, 32000, 10, 21),
        ],
    },
    {
        "name": "Apollo Hospitals Chennai",
        "country": "IN",
        "city": "Chennai",
        "specialties": ["orthopedics", "transplant", "cardiology"],
        "accreditations": ["JCI", "NABH"],
        "languages": ["en", "hi", "ta"],
        "avg_rating": Decimal("4.40"),
        "bed_count": 1000,
        "intl_patient_services": True,
        "latitude": Decimal("13.035800"),
        "longitude": Decimal("80.248200"),
        "established_year": 1983,
        "procedures": [
            ("TKR-001", "Total knee replacement", 6500, 9500, 6, 7),
            ("HIP-001", "Total hip replacement", 7000, 10500, 7, 10),
        ],
    },
    {
        "name": "Acibadem Maslak Hospital",
        "country": "TR",
        "city": "Istanbul",
        "specialties": ["oncology", "orthopedics", "neurosurgery"],
        "accreditations": ["JCI", "ISO 9001"],
        "languages": ["en", "tr", "de", "ru"],
        "avg_rating": Decimal("4.50"),
        "bed_count": 230,
        "intl_patient_services": True,
        "latitude": Decimal("41.110600"),
        "longitude": Decimal("29.020600"),
        "established_year": 2007,
        "procedures": [
            ("TKR-001", "Total knee replacement", 9000, 13000, 6, 10),
            ("SPINE-001", "Lumbar spinal fusion", 14000, 19000, 8, 12),
        ],
    },
    {
        "name": "Hospital Angeles Tijuana",
        "country": "MX",
        "city": "Tijuana",
        "specialties": ["bariatrics", "orthopedics", "dentistry"],
        "accreditations": ["CSG"],
        "languages": ["es", "en"],
        "avg_rating": Decimal("4.10"),
        "bed_count": 130,
        "intl_patient_services": True,
        "latitude": Decimal("32.521100"),
        "longitude": Decimal("-117.011900"),
        "established_year": 2006,
        "procedures": [
            ("BARI-001", "Gastric sleeve", 5500, 8000, 3, 5),
            ("TKR-001", "Total knee replacement", 11000, 15000, 6, 9),
        ],
    },
]


def seed_users(db: Session) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, role, full_name, country in USERS:
        existing = db.scalars(select(User).where(User.email == email)).first()
        if existing:
            users[email] = existing
            print(f"  = user {email} already exists")
            continue
        profile = (
            PatientProfileIn(full_name=full_name, country=country) if full_name else None
        )
        users[email] = create_user(
            db, email=email, password=DEMO_PASSWORD, role=role, profile=profile
        )
        print(f"  + user {email} ({role.value})")
    return users


def seed_providers(db: Session) -> None:
    for spec in PROVIDERS:
        procedures = spec.pop("procedures")
        existing = db.scalars(select(Provider).where(Provider.name == spec["name"])).first()
        if existing:
            print(f"  = provider {spec['name']} already exists")
            spec["procedures"] = procedures
            continue

        provider = Provider(**spec)
        db.add(provider)
        db.flush()
        for code, name, low, high, stay, wait in procedures:
            db.add(
                ProcedurePrice(
                    provider_id=provider.id,
                    procedure_code=code,
                    procedure_name=name,
                    price_min_usd=Decimal(low),
                    price_max_usd=Decimal(high),
                    typical_stay_days=stay,
                    wait_time_days=wait,
                )
            )
        print(f"  + provider {provider.name} ({len(procedures)} procedures)")
        spec["procedures"] = procedures
    db.commit()


def seed_cases(db: Session, users: dict[str, User]) -> None:
    patient = users["patient@example.com"]
    coordinator = users["coordinator@example.com"]

    if db.scalars(select(Case).where(Case.patient_id == patient.id)).first():
        print("  = demo cases already exist")
        return

    draft = Case(
        patient_id=patient.id,
        procedure_code="TKR-001",
        target_countries=["IN", "TH"],
        status=CaseStatus.DRAFT,
    )
    reviewing = Case(
        patient_id=patient.id,
        coordinator_id=coordinator.id,
        procedure_code="HIP-001",
        target_countries=["IN"],
        status=CaseStatus.UNDER_REVIEW,
    )
    db.add_all([draft, reviewing])
    db.flush()

    for case in (draft, reviewing):
        record_event(
            db,
            case=case,
            actor_id=patient.id,
            event_type=CaseEventType.CASE_CREATED,
            payload={"procedure_code": case.procedure_code, "seeded": True},
        )
    record_event(
        db,
        case=reviewing,
        actor_id=coordinator.id,
        event_type=CaseEventType.COORDINATOR_ASSIGNED,
        payload={"from": None, "to": str(coordinator.id)},
    )
    record_event(
        db,
        case=reviewing,
        actor_id=coordinator.id,
        event_type=CaseEventType.STATUS_CHANGED,
        payload={"from": "submitted", "to": "under_review", "reason": "seeded"},
    )
    db.commit()
    print("  + 2 demo cases")


def reset(db: Session) -> None:
    emails = [email for email, *_ in USERS]
    names = [spec["name"] for spec in PROVIDERS]
    # Cases, events, and profiles go with the users via ON DELETE CASCADE.
    for user in db.scalars(select(User).where(User.email.in_(emails))):
        db.delete(user)
    for provider in db.scalars(select(Provider).where(Provider.name.in_(names))):
        db.delete(provider)
    db.commit()
    print("  - removed previously seeded rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete seeded rows first")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            print("Resetting:")
            reset(db)
        print("Users:")
        users = seed_users(db)
        print("Providers:")
        seed_providers(db)
        print("Cases:")
        seed_cases(db, users)

    print(f"\nDone. Every demo account uses the password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
