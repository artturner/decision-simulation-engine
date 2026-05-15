"""
FastAPI application factory.

Usage
-----
Start the dev server from ``services/api/``::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.admin import router as admin_router
from app.api.v1.public import router as public_router
from app.core.config import settings

app = FastAPI(
    title="Branching Scenarios API",
    version="0.1.0",
    description="Admin and public API for the Branching Scenarios MVP.",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(admin_router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Media static files
# ---------------------------------------------------------------------------

_media_dir = "media"  # relative to the CWD (project root when run with uvicorn)
os.makedirs(_media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_dir), name="media")

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["meta"], summary="Health check")
def health() -> dict:
    return {"status": "ok"}
