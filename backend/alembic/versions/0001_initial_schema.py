"""Initial schema: users, providers, cases, documents, audit trail

Revision ID: 0001
Revises:
Create Date: 2026-09-20

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


user_role = postgresql.ENUM(
    "patient", "coordinator", "admin", name="user_role", create_type=False
)
case_status = postgresql.ENUM(
    "draft",
    "submitted",
    "under_review",
    "provider_matched",
    "quoted",
    "scheduled",
    "completed",
    "cancelled",
    name="case_status",
    create_type=False,
)
document_status = postgresql.ENUM(
    "pending", "processing", "processed", "failed", name="document_status", create_type=False
)
document_type = postgresql.ENUM(
    "lab_report",
    "imaging",
    "discharge_summary",
    "insurance",
    "other",
    name="document_type",
    create_type=False,
)
case_event_type = postgresql.ENUM(
    "case_created",
    "status_changed",
    "coordinator_assigned",
    "provider_shortlisted",
    "provider_removed",
    "quote_recorded",
    "document_uploaded",
    "document_processed",
    "document_failed",
    "document_deleted",
    name="case_event_type",
    create_type=False,
)

ALL_ENUMS = (user_role, case_status, document_status, document_type, case_event_type)

# Keeps providers.search_vector in step with the columns people actually search on.
# A generated column will not do here: array_to_string() is only STABLE, not IMMUTABLE.
SEARCH_VECTOR_FUNCTION = """
CREATE OR REPLACE FUNCTION providers_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.name, '')), 'A') ||
        setweight(
            to_tsvector('english', coalesce(array_to_string(NEW.specialties, ' '), '')),
            'B'
        ) ||
        setweight(to_tsvector('english', coalesce(NEW.city, '')), 'C') ||
        setweight(
            to_tsvector('english', coalesce(array_to_string(NEW.accreditations, ' '), '')),
            'D'
        );
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

SEARCH_VECTOR_TRIGGER = """
CREATE TRIGGER providers_search_vector_trigger
BEFORE INSERT OR UPDATE OF name, specialties, city, accreditations ON providers
FOR EACH ROW EXECUTE FUNCTION providers_search_vector_update();
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "patient_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("preferred_language", sa.String(16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patient_profiles_user_id", "patient_profiles", ["user_id"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column(
            "specialties",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "accreditations",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "languages",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("avg_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("bed_count", sa.Integer(), nullable=True),
        sa.Column(
            "intl_patient_services",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("established_year", sa.Integer(), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "avg_rating IS NULL OR (avg_rating >= 0 AND avg_rating <= 5)",
            name="ck_providers_avg_rating_range",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_providers_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_providers_longitude_range",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_providers_country", "providers", ["country"])
    op.create_index(
        "ix_providers_search_vector", "providers", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_providers_specialties", "providers", ["specialties"], postgresql_using="gin"
    )
    op.create_index("ix_providers_languages", "providers", ["languages"], postgresql_using="gin")
    op.create_index(
        "ix_providers_name_trgm",
        "providers",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.execute(SEARCH_VECTOR_FUNCTION)
    op.execute(SEARCH_VECTOR_TRIGGER)

    op.create_table(
        "procedure_prices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("procedure_code", sa.String(32), nullable=False),
        sa.Column("procedure_name", sa.String(200), nullable=False),
        sa.Column("price_min_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_max_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("typical_stay_days", sa.Integer(), nullable=True),
        sa.Column("wait_time_days", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price_min_usd >= 0", name="ck_procedure_prices_min_non_negative"),
        sa.CheckConstraint(
            "price_max_usd >= price_min_usd", name="ck_procedure_prices_max_gte_min"
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id", "procedure_code", name="uq_procedure_prices_provider_code"
        ),
    )
    op.create_index("ix_procedure_prices_provider_id", "procedure_prices", ["provider_id"])
    op.create_index("ix_procedure_prices_procedure_code", "procedure_prices", ["procedure_code"])

    op.create_table(
        "cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coordinator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("procedure_code", sa.String(32), nullable=False),
        sa.Column("status", case_status, server_default="draft", nullable=False),
        sa.Column(
            "target_countries",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coordinator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_patient_id", "cases", ["patient_id"])
    op.create_index("ix_cases_coordinator_id", "cases", ["coordinator_id"])
    op.create_index("ix_cases_procedure_code", "cases", ["procedure_code"])
    op.create_index("ix_cases_status_created_at", "cases", ["status", "created_at"])
    op.create_index(
        "ix_cases_unassigned_queue",
        "cases",
        ["created_at"],
        postgresql_where=sa.text("coordinator_id IS NULL"),
    )

    op.create_table(
        "case_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shortlisted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quoted_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shortlisted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "provider_id", name="uq_case_providers_case_provider"),
    )
    op.create_index("ix_case_providers_case_id", "case_providers", ["case_id"])
    op.create_index("ix_case_providers_provider_id", "case_providers", ["provider_id"])

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", document_status, server_default="pending", nullable=False),
        sa.Column("doc_type", document_type, server_default="other", nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_documents_size_non_negative"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key", name="uq_documents_s3_key"),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"])

    op.create_table(
        "case_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", case_event_type, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"])
    op.create_index("ix_case_events_case_id_created_at", "case_events", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_table("case_events")
    op.drop_table("documents")
    op.drop_table("case_providers")
    op.drop_table("cases")
    op.drop_table("procedure_prices")
    op.execute("DROP TRIGGER IF EXISTS providers_search_vector_trigger ON providers")
    op.execute("DROP FUNCTION IF EXISTS providers_search_vector_update()")
    op.drop_table("providers")
    op.drop_table("refresh_tokens")
    op.drop_table("patient_profiles")
    op.drop_table("users")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
