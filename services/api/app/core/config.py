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
    # point this at your CDN or static file server.  Locally, the API
    # serves media from /media so http://localhost:8000/media works.
    MEDIA_BASE_URL: str = "http://localhost:8000/media"

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # Shared secret for admin endpoints.  In production this must be set
    # via the ADMIN_API_KEY environment variable.
    ADMIN_API_KEY: str = "changeme"

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
