"""
Minimal per-IP rate limiting for abuse-prone public endpoints.

Implemented as a FastAPI dependency factory rather than slowapi: slowapi's
decorator rewrites the endpoint signature and cannot resolve this codebase's
postponed annotations (``from __future__ import annotations``), which broke
request-body parsing. A sliding-window counter in process memory is enough —
the API runs as a single Railway container.

Behind Railway's proxy the client address arrives in ``X-Forwarded-For``;
``request.client.host`` would rate-limit all traffic as one proxy IP.

Usage::

    @router.post("/plays/start", dependencies=[Depends(limiter.limit("start", 30, 60))])
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window request counter keyed by (bucket, client IP)."""

    def __init__(self) -> None:
        self.enabled = True
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def limit(self, bucket: str, times: int, seconds: float):
        """Return a dependency allowing *times* requests per *seconds* per IP."""

        def dependency(request: Request) -> None:
            if not self.enabled:
                return
            key = f"{bucket}|{client_ip(request)}"
            now = time.monotonic()
            cutoff = now - seconds
            with self._lock:
                hits = self._hits.setdefault(key, deque())
                while hits and hits[0] < cutoff:
                    hits.popleft()
                if not hits and len(self._hits) > 10_000:
                    # Opportunistic cleanup so idle keys don't accumulate.
                    for stale in [k for k, v in self._hits.items() if not v]:
                        if stale != key:
                            del self._hits[stale]
                if len(hits) >= times:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many requests. Please wait a moment and try again.",
                    )
                hits.append(now)

        return dependency


limiter = RateLimiter()
