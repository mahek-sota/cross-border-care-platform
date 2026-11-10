# CLAUDE.md

Guidance for working in this repo. See `README.md` for setup and what is built.

## Tech stack — fixed, do not substitute

React (Vite + TS) · React Router · TanStack Query · Tailwind · FastAPI · Pydantic v2 ·
SQLAlchemy 2.0 + Alembic · PostgreSQL 16 · Celery + Redis · S3 (MinIO locally) ·
JWT with passlib/bcrypt.

## Commands

```bash
# Backend (from backend/, venv at backend/.venv)
.venv/bin/python -m pytest
.venv/bin/ruff check app tests alembic
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "description"

# Frontend (from frontend/)
npm run typecheck && npm run build

# Stack
docker compose -f infra/docker-compose.yml up --build
python scripts/seed.py [--reset]
```

Tests need PostgreSQL. `docker compose -f infra/docker-compose.yml up -d postgres`.
Host ports are all overridable in `infra/.env`; this machine uses non-default ones
because other projects hold 5432/6379/8000/9000.

## Rules that matter

**Access control belongs in `app/api/deps.py`.** `case_access_filter(user)` is the
single source of truth for case visibility. `get_case_for_user` and every list
endpoint build on it. Never hand-roll `case.patient_id == current_user.id` in an
endpoint — if a new resource needs scoping, add a filter function next to that one and
a dependency that uses it.

**Out-of-scope objects return 404, not 403.** A 403 confirms the row exists.

**Role comes from the database, never the token.** `get_current_user` loads the user
on every request. The `role` claim in the JWT is informational only.

**Every case mutation writes a `CaseEvent`** via `record_event` in
`app/services/case_events.py`, staged on the same session and committed in the same
transaction as the change. Never `db.commit()` the change and the event separately,
and never write a `CaseEvent` row directly. Failed operations write nothing.

**Never assign a filtered list to a delete-orphan relationship.**
`Provider.procedures` and `Case.documents`/`events` are `delete-orphan`; narrowing one
in place marks the excluded rows as orphans and deletes them on the next flush. Return
the filtered list alongside the object instead — see `compare_providers`, which has a
regression test.

**Business rules live in `app/services/`, not in routers.** Routers resolve
dependencies, call a service, and serialize. The case transition table is
`ALLOWED_TRANSITIONS` in `app/services/cases.py`.

**Migrations are hand-checked.** `--autogenerate` misses triggers, partial indexes,
GIN opclasses, and extension creation — all of which migration 0001 relies on. Always
read the generated file before committing it, and always verify `downgrade()`.

**Enums are Postgres enum types.** Adding a value needs an `ALTER TYPE ... ADD VALUE`
migration alongside the Python `StrEnum` change.

## Conventions

- Python: 100-col lines, `from __future__ import annotations`, SQLAlchemy 2.0
  `Mapped`/`mapped_column`, UUID primary keys with `gen_random_uuid()` server default.
- Timestamps are `TIMESTAMPTZ`; use `datetime.now(UTC)`, never naive datetimes.
- Money is `Numeric(12, 2)`, never float.
- Country codes are ISO 3166-1 alpha-2, uppercase, normalized at the schema boundary.
- Frontend: all HTTP goes through `src/lib/api.ts`. Do not call `fetch` from a
  component — the client handles token refresh and error shaping in one place.
- Tests name the behaviour, not the function: `test_patient_cannot_read_another_patients_case`.

## Not yet built

The document upload + Celery extraction pipeline (`Document` model, S3 settings, and
the worker skeleton exist; `app/worker/tasks.py` has only a `ping` task) and the full
case workflow. The spec for these was truncated; ask before inventing requirements.

Provider search exists but is **not connected to cases**: the `CaseProvider` model
(shortlisting, quoted price, notes) has no endpoint and no UI, so the compare view is
currently a dead end — you can compare providers but not attach one to a case.
