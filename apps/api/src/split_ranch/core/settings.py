"""Application settings loaded from the environment (see docs/11 `.env.example`)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"

    # API connection (transaction pooler in the cloud).
    database_url: str = "postgresql+psycopg://split_api:split_api@localhost:54322/postgres"
    # Worker + migrations (session pooler / direct: LISTEN/NOTIFY needs a session).
    database_url_session: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5

    supabase_url: str = "http://localhost:54321"
    supabase_jwt_issuer: str | None = None
    supabase_jwks_url: str | None = None
    supabase_secret_key: str | None = None
    jwt_audience: str = "authenticated"
    jwt_leeway_seconds: int = 30
    jwks_cache_seconds: int = 600

    # Process-local cache for ensure_user (seconds); 0 disables it.
    ensure_user_cache_seconds: int = 300

    sentry_dsn: str | None = None
    log_level: str = "INFO"
    log_json: bool = True

    min_app_version: str = "0.1.0"
    public_web_url: str = "https://split.ranch"
    quick_share_days: int = Field(default=90, ge=1, le=3650)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_issuer(self) -> str:
        return self.supabase_jwt_issuer or f"{self.supabase_url.rstrip('/')}/auth/v1"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwks_url(self) -> str:
        return (
            self.supabase_jwks_url
            or f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        )

    @property
    def session_database_url(self) -> str:
        return self.database_url_session or self.database_url


def libpq_url(sqlalchemy_url: str) -> str:
    """Convert a SQLAlchemy URL (postgresql+psycopg://) into a libpq conninfo URL."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if sqlalchemy_url.startswith(prefix):
            return "postgresql://" + sqlalchemy_url[len(prefix) :]
    return sqlalchemy_url


def sqlalchemy_url(url: str) -> str:
    """Normalise a libpq or SQLAlchemy URL to the psycopg 3 SQLAlchemy dialect."""
    for prefix in ("postgresql+psycopg2://", "postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
