"""Unit tests for the in-house per-IP rate limiter (app.core.ratelimit)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.ratelimit import RateLimiter, client_ip


def _request(ip: str = "1.2.3.4", forwarded: str | None = None):
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=ip))


class TestClientIp:
    def test_prefers_first_forwarded_hop(self):
        req = _request(ip="10.0.0.1", forwarded="203.0.113.9, 10.0.0.2")
        assert client_ip(req) == "203.0.113.9"

    def test_falls_back_to_client_host(self):
        assert client_ip(_request(ip="203.0.113.7")) == "203.0.113.7"


class TestRateLimiter:
    def test_blocks_after_limit_within_window(self):
        limiter = RateLimiter()
        dep = limiter.limit("test", times=3, seconds=60)
        for _ in range(3):
            dep(_request())
        with pytest.raises(HTTPException) as exc:
            dep(_request())
        assert exc.value.status_code == 429

    def test_ips_are_counted_independently(self):
        limiter = RateLimiter()
        dep = limiter.limit("test", times=1, seconds=60)
        dep(_request(ip="1.1.1.1"))
        dep(_request(ip="2.2.2.2"))  # different IP: not blocked
        with pytest.raises(HTTPException):
            dep(_request(ip="1.1.1.1"))

    def test_buckets_are_counted_independently(self):
        limiter = RateLimiter()
        a = limiter.limit("bucket-a", times=1, seconds=60)
        b = limiter.limit("bucket-b", times=1, seconds=60)
        a(_request())
        b(_request())  # same IP, different bucket: not blocked

    def test_disabled_limiter_never_blocks(self):
        limiter = RateLimiter()
        limiter.enabled = False
        dep = limiter.limit("test", times=1, seconds=60)
        for _ in range(10):
            dep(_request())
