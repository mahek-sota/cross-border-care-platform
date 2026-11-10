from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# app/core/config.py -> app/core -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Anchored to the backend directory rather than the process working directory,
    # so `python scripts/seed.py` from the repo root reads the same config as
    # `alembic upgrade head` from backend/. Later files win; real env vars beat both.
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / "infra" / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"

    # --- Database ---
    database_url: str = "postgresql+psycopg://cbcare:cbcare@localhost:5432/cbcare"
    test_database_url: str | None = None

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- JWT ---
    jwt_secret_key: str = "dev-only-insecure-key-replace-before-deploying"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # --- S3 / MinIO ---
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "cbcare-documents"
    s3_region: str = "us-east-1"

    # --- CORS ---
    # NoDecode: take the raw env string and split it on commas ourselves, rather than
    # letting pydantic-settings insist on JSON for a list-typed field.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
