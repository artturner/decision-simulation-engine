"""
Application settings loaded from environment variables (or a .env file).

All settings have sensible defaults that work with the docker-compose stack
defined in infra/docker-compose.yml so developers can start without any
manual configuration.

Usage
-----
    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL)
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql://branching:branching@localhost:5432/branching_scenarios"
    )

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------
    # Base URL used to construct absolute image URLs.  In production,
    # set this to R2_PUBLIC_URL so image URLs resolve against R2.
    # Locally, the API serves media from /media so http://localhost:8000/media works.
    MEDIA_BASE_URL: str = "http://localhost:8000/media"

    # ------------------------------------------------------------------
    # Cloudflare R2 (optional — leave blank to use local disk in dev)
    # ------------------------------------------------------------------
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    # Public URL for the bucket, e.g. https://pub-abc123.r2.dev
    # or a custom domain like https://media.yourapp.com
    R2_PUBLIC_URL: str = ""

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # Shared secret for admin endpoints.  In production this must be set
    # via the ADMIN_API_KEY environment variable.
    ADMIN_API_KEY: str = "changeme"

    # JWT secret from Supabase project settings → API → JWT Secret.
    # Used to verify tokens issued by Supabase Auth for teacher accounts.
    JWT_SECRET: str = "changeme-jwt-secret"

    # JWT algorithm — Supabase uses HS256 by default.
    JWT_ALGORITHM: str = "HS256"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    # Comma-separated list of allowed origins, e.g.
    # "http://localhost:3000,https://myapp.example.com"
    CORS_ORIGINS: str = "http://localhost:3000"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> object:
        # Accept either a plain string or an already-split list from env.
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS split on commas, stripped of whitespace."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
