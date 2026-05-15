"""
Unit tests for the verify_admin_key dependency.

These tests use TestClient with a minimal FastAPI app — no database required.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import verify_admin_key
from app.api.v1.admin import router as admin_router
from app.core.config import settings


# ---------------------------------------------------------------------------
# Minimal app wired with the admin router
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(admin_router, prefix="/api/v1")

# A tiny probe route added directly (for dependency unit-testing)
probe_app = FastAPI()


@probe_app.get("/probe", dependencies=[__import__("fastapi").Depends(verify_admin_key)])
def probe():
    return {"ok": True}


probe_client = TestClient(probe_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# verify_admin_key — unit tests via the probe route
# ---------------------------------------------------------------------------


class TestVerifyAdminKey:
    def test_valid_key_returns_200(self):
        resp = probe_client.get("/probe", headers={"X-Admin-Key": settings.ADMIN_API_KEY})
        assert resp.status_code == 200

    def test_missing_key_returns_403(self):
        resp = probe_client.get("/probe")
        assert resp.status_code == 403

    def test_wrong_key_returns_403(self):
        resp = probe_client.get("/probe", headers={"X-Admin-Key": "wrong-key"})
        assert resp.status_code == 403

    def test_empty_key_returns_403(self):
        resp = probe_client.get("/probe", headers={"X-Admin-Key": ""})
        assert resp.status_code == 403

    def test_403_detail_message(self):
        resp = probe_client.get("/probe")
        assert "detail" in resp.json()

    def test_case_sensitive_key(self):
        """Key comparison must be case-sensitive."""
        wrong = settings.ADMIN_API_KEY.upper()
        if wrong == settings.ADMIN_API_KEY:
            pytest.skip("ADMIN_API_KEY is already all-caps — cannot test case sensitivity")
        resp = probe_client.get("/probe", headers={"X-Admin-Key": wrong})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# admin router — dependency applied at router level
# ---------------------------------------------------------------------------


class TestAdminRouterAuth:
    """Verify the admin router rejects requests without a valid key.

    The router has no routes yet (they're added in subsequent prompts), so we
    verify that a request to any non-existent path still returns 403 (not 404)
    when the key is missing — meaning the dependency fires before path matching
    would normally 404.

    NOTE: FastAPI actually runs path matching first and returns 404 for unknown
    paths even if the dependency would 403.  So instead we just confirm the
    router is mounted correctly by checking the OpenAPI schema tags.
    """

    def test_admin_router_tag(self):
        """Router is registered with the 'admin' tag."""
        client = TestClient(app, raise_server_exceptions=False)
        schema = client.get("/openapi.json").json()
        tags = {tag["name"] for tag in schema.get("tags", [])}
        # The router declares tags=["admin"] so it should appear
        paths = schema.get("paths", {})
        # With no routes yet, paths is empty — just confirm import works
        assert admin_router.prefix == "/admin"
        assert "admin" in admin_router.tags
