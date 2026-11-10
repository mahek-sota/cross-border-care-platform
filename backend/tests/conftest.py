"""Test harness.

Tests run against a real PostgreSQL database -- the schema leans on arrays, JSONB,
enums, partial indexes and pg_trgm, none of which SQLite can stand in for. The test
database is created once per session and migrated with Alembic, so the migration
itself is exercised on every run. Tables are truncated between tests.

Point ``TEST_DATABASE_URL`` at your Postgres instance, or start one with:
    docker compose -f infra/docker-compose.yml up -d postgres
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.services import auth as auth_service

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or settings.test_database_url
    or "postgresql+psycopg://cbcare:cbcare@localhost:5432/cbcare_test"
)


def _ensure_database_exists(url: str) -> None:
    target = sa.engine.make_url(url)
    admin_url = target.set(database="postgres")
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                conn.execute(sa.text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[sa.Engine]:
    try:
        _ensure_database_exists(TEST_DATABASE_URL)
    except sa.exc.OperationalError as exc:  # pragma: no cover - environment problem
        pytest.skip(f"PostgreSQL is not reachable at {TEST_DATABASE_URL}: {exc}")

    test_engine = sa.create_engine(TEST_DATABASE_URL, poolclass=sa.pool.NullPool)

    # Start from an empty schema so a half-migrated database from an aborted run
    # cannot make this one pass or fail spuriously.
    with test_engine.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA public"))

    alembic_cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    yield test_engine
    test_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: sa.Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def clean_tables(engine: sa.Engine) -> Iterator[None]:
    yield
    table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# User + auth helpers
# --------------------------------------------------------------------------- #

DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(db: Session):
    def _make_user(
        role: UserRole = UserRole.PATIENT,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
    ) -> User:
        return auth_service.create_user(
            db,
            email=email or f"{role.value}-{uuid.uuid4().hex[:8]}@example.com",
            password=password,
            role=role,
        )

    return _make_user


@pytest.fixture
def auth_headers(client: TestClient):
    """Log a user in and return an Authorization header dict for them."""

    def _auth_headers(user: User, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": password}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth_headers


@pytest.fixture
def patient(make_user) -> User:
    return make_user(UserRole.PATIENT)


@pytest.fixture
def other_patient(make_user) -> User:
    return make_user(UserRole.PATIENT)


@pytest.fixture
def coordinator(make_user) -> User:
    return make_user(UserRole.COORDINATOR)


@pytest.fixture
def other_coordinator(make_user) -> User:
    return make_user(UserRole.COORDINATOR)


@pytest.fixture
def admin(make_user) -> User:
    return make_user(UserRole.ADMIN)
