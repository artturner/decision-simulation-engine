from __future__ import annotations

import time
import uuid
from base64 import urlsafe_b64encode

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt

from app.api import deps


def _es256_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes(32, byteorder="big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_jwk(public_key, kid: str) -> dict:
    numbers = public_key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url_uint(numbers.x),
        "y": _b64url_uint(numbers.y),
        "alg": "ES256",
        "kid": kid,
        "use": "sig",
    }


def test_decode_teacher_token_uses_supabase_jwks(monkeypatch):
    private_key, public_key = _es256_keypair()
    token_kid = "test-key"
    user_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": "teacher@example.com",
            "role": "authenticated",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": token_kid},
    )
    jwk = _public_jwk(public_key, token_kid)

    monkeypatch.setattr(deps.settings, "SUPABASE_JWKS_URL", "https://example.test/jwks")
    monkeypatch.setattr(deps, "_fetch_jwks", lambda _url: {"keys": [jwk]})

    payload = deps._decode_teacher_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["email"] == "teacher@example.com"


def test_decode_teacher_token_rejects_unknown_jwks_key(monkeypatch):
    private_key, public_key = _es256_keypair()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "teacher@example.com",
            "exp": int(time.time()) + 300,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "token-key"},
    )
    jwk = _public_jwk(public_key, "different-key")

    monkeypatch.setattr(deps.settings, "SUPABASE_JWKS_URL", "https://example.test/jwks")
    monkeypatch.setattr(deps.settings, "JWT_SECRET", "legacy-secret")
    monkeypatch.setattr(deps, "_fetch_jwks", lambda _url: {"keys": [jwk]})

    with pytest.raises(Exception) as exc:
        deps._decode_teacher_token(token)

    assert getattr(exc.value, "status_code", None) == 401


def test_decode_teacher_token_supports_explicit_legacy_secret(monkeypatch):
    user_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": "teacher@example.com",
            "exp": int(time.time()) + 300,
        },
        "real-legacy-secret",
        algorithm="HS256",
    )

    monkeypatch.setattr(deps.settings, "SUPABASE_JWKS_URL", "")
    monkeypatch.setattr(deps.settings, "SUPABASE_URL", "")
    monkeypatch.setattr(deps.settings, "JWT_SECRET", "real-legacy-secret")

    payload = deps._decode_teacher_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["email"] == "teacher@example.com"
