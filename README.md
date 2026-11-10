# Cross-Border Care Coordination Platform

Helps patients seeking treatment abroad compare providers, submit medical records, and
track their case, while coordinators manage those cases from the other side.

## Status

| Area | State |
| --- | --- |
| Repo scaffold, docker-compose, Dockerfiles | done |
| Full domain model + initial Alembic migration | done |
| **Feature 1 — Auth + RBAC** | done, 42 tests passing |
| **Provider search + compare** | done, 37 tests passing |
| Frontend (login, register, provider search/detail/compare, cases) | done |
| Seed script (5 users, 4 providers, 8 procedure prices, 2 cases) | done |
| Documents / OCR pipeline, full case workflow | **not started — spec truncated** |

The case status/assignment endpoints that exist today are a thin, deliberately
conservative first pass, written so the object-level access rules have something real
to guard. The transition table lives in one place (`backend/app/services/cases.py`)
and is expected to be replaced once the case-workflow spec lands.

## Quick start

```bash
cp infra/.env.example infra/.env        # edit host ports if any collide
docker compose -f infra/docker-compose.yml up --build
```

Then:

- API + OpenAPI docs: <http://localhost:8000/docs>
- Web app: <http://localhost:5173>
- MinIO console: <http://localhost:9001> (`minioadmin` / `minioadmin`)

Apply migrations and load demo data:

```bash
docker compose -f infra/docker-compose.yml exec api alembic upgrade head
docker compose -f infra/docker-compose.yml exec api python ../scripts/seed.py
```

### Port conflicts

Every host port is overridable in `infra/.env` — `POSTGRES_PORT`, `REDIS_PORT`,
`MINIO_PORT`, `MINIO_CONSOLE_PORT`, `API_PORT`, `WEB_PORT`. Change them there if
something else on your machine already owns the default.

## Running without Docker

```bash
# Postgres only
docker compose -f infra/docker-compose.yml up -d postgres

cd backend
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload

cd ../frontend && npm install && npm run dev
```

`DATABASE_URL` / `TEST_DATABASE_URL` in `infra/.env` are what host-side commands use;
docker compose overrides them for the containers.

## Tests

```bash
cd backend && .venv/bin/python -m pytest        # 79 tests
cd backend && .venv/bin/ruff check app tests alembic
cd frontend && npm run typecheck && npm run build
```

Tests run against a **real PostgreSQL database** — the schema uses arrays, JSONB,
enums, partial indexes, and `pg_trgm`, so SQLite is not a usable stand-in. The suite
creates `cbcare_test`, drops and re-migrates the schema with Alembic on every run
(which exercises the migration itself), and truncates tables between tests. If
Postgres is unreachable the suite skips rather than fails.

## Demo accounts

All use the password `correct-horse-battery`:

| Email | Role |
| --- | --- |
| `patient@example.com` | patient (owns both demo cases) |
| `patient2@example.com` | patient (sees nothing of patient 1) |
| `coordinator@example.com` | coordinator (one case assigned) |
| `coordinator2@example.com` | coordinator (sees only the unassigned queue) |
| `admin@example.com` | admin |

## Auth model

- **Access token**: stateless JWT, 15 minutes, carries `sub`/`role`/`type`/`jti`.
- **Refresh token**: 14 days, and its `jti` is recorded in `refresh_tokens`. Logout
  revokes the row, and `/refresh` rotates unconditionally — a refresh token is
  single-use, so a stolen one stops working the moment the real holder refreshes.
- The caller's **role is read from the database on every request**, not trusted from
  the token, so a demotion takes effect immediately rather than at token expiry.
- `POST /auth/register` always creates a patient; a `role` in the body is ignored.
  Coordinators and admins are provisioned by an admin via `POST /auth/users`.

### RBAC

Role gating uses `require_role(*roles)`. Object-level access has exactly one
implementation — `case_access_filter(user)` in `backend/app/api/deps.py`:

| Role | Cases visible |
| --- | --- |
| patient | only their own |
| coordinator | assigned to them, plus unassigned ones in the queue |
| admin | all |

`get_case_for_user` (the single-case dependency) and every list endpoint build on that
same SQL clause, so listing and fetching can never disagree — a case you cannot `GET`
can never show up in your list. Cases outside your scope return **404, not 403**, so
the API never confirms that another patient's case exists. There is a test for this.

## Provider search

`GET /api/v1/providers` — text search plus filters, sorting, and pagination.

| Parameter | Notes |
| --- | --- |
| `q` | Free text over name, specialties, city, accreditations |
| `country` | Repeatable; ISO-2, case-insensitive |
| `specialty`, `language`, `accreditation` | Repeatable; array overlap (match any) |
| `procedure_code` | Restricts to providers offering it and attaches the price |
| `max_price_usd` | With a procedure, filters that price; without one, matches any procedure |
| `min_rating` | Unrated providers are excluded — NULL means unknown, not zero |
| `intl_patient_services` | Boolean |
| `sort` | `relevance` (default), `price`, `rating`, `name` |

Also `GET /providers/{id}`, `GET /providers/facets` (filter values with counts), and
`GET /providers/compare?ids=…&procedure_code=…` (2–4 providers side by side).

Text search deliberately combines two mechanisms, because they fail in opposite ways:

- **`tsvector`** matches meaning — "oncological" finds a provider whose specialty is
  "oncology" — but cannot survive a misspelling.
- **`pg_trgm` similarity** matches spelling — "bumrangrad" still finds "Bumrungrad" —
  but understands nothing.

A provider matches if either hits; the score sums both with full-text weighted 2×, so
a real term match outranks a lucky fuzzy one. Input goes through
`websearch_to_tsquery`, which never raises a syntax error on stray punctuation, so no
sanitising is needed — there is a test that feeds it `'unbalanced` and `<->`.

Sorting by `price` without a `procedure_code` has no single price to rank on, so it
falls back to rating rather than returning an arbitrary order; the UI says so.

## Layout

```
backend/     FastAPI app, alembic/, tests/
  app/core       config, JWT + password hashing
  app/models     SQLAlchemy 2.0 models, enums
  app/schemas    Pydantic v2 request/response models
  app/api        deps.py (auth + RBAC), v1/ routers
  app/services   auth, cases, case_events (audit trail), providers (search)
  app/worker     Celery app + tasks
frontend/    React + Vite + TS, TanStack Query, Tailwind v4
infra/       docker-compose.yml, Dockerfiles, .env.example
scripts/     seed.py
```

## Notes on the schema

- `providers.search_vector` is maintained by a trigger, not a generated column —
  `array_to_string()` is only `STABLE`, so Postgres rejects it in a generated column.
  Weighted: name (A), specialties (B), city (C), accreditations (D).
- `pg_trgm` GIN index on `providers.name` for fuzzy matching; GIN indexes on the
  `specialties` and `languages` arrays.
- `cases` has a partial index on `created_at WHERE coordinator_id IS NULL` for the
  coordinator intake queue.
- `case_events` is append-only. Every write goes through `record_event`, which stages
  the row on the caller's session without committing, so the event and the change it
  describes land in the same transaction. A rejected transition writes no event —
  there is a test for that too.
