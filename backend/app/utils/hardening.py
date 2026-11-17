"""Production safeguards: login throttling, security headers, request ids, error handling."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger("app.access")

# --------------------------------------------------------------------------- login throttle
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 8

_memory_failures: dict[str, deque] = defaultdict(deque)
_memory_lock = threading.Lock()


def _throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"login:fail:{ip}:{email.lower()}"


def _failures(key: str) -> int:
    try:
        from app.redis_client import get_redis

        return int(get_redis().get(key) or 0)
    except Exception:  # noqa: BLE001 - fall back to per-process memory
        with _memory_lock:
            q = _memory_failures[key]
            while q and q[0] < time.time() - LOGIN_WINDOW_SECONDS:
                q.popleft()
            return len(q)


def check_login_allowed(request: Request, email: str) -> None:
    if _failures(_throttle_key(request, email)) >= LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please wait 15 minutes and try again.",
        )


def record_login_failure(request: Request, email: str) -> None:
    key = _throttle_key(request, email)
    try:
        from app.redis_client import get_redis

        r = get_redis()
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOGIN_WINDOW_SECONDS)
        pipe.execute()
    except Exception:  # noqa: BLE001
        with _memory_lock:
            _memory_failures[key].append(time.time())


def clear_login_failures(request: Request, email: str) -> None:
    key = _throttle_key(request, email)
    try:
        from app.redis_client import get_redis

        get_redis().delete(key)
    except Exception:  # noqa: BLE001
        with _memory_lock:
            _memory_failures.pop(key, None)


# --------------------------------------------------------------------------- middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Request id, timing log and conservative security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/") and request.url.path not in ("/api/v1/health",):
            logger.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code, elapsed_ms, request_id)
        return response


def install(app: FastAPI) -> None:
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
        rid = getattr(request.state, "request_id", "-")
        logging.getLogger("app.errors").exception("Unhandled error rid=%s on %s %s", rid, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our side. Please try again.", "request_id": rid},
        )


def validate_settings() -> list[str]:
    """Return configuration problems; in production they stop the server from starting."""
    problems = []
    if len(settings.JWT_SECRET) < 32 or "change_this" in settings.JWT_SECRET:
        problems.append("JWT_SECRET must be a random string of at least 32 characters")
    if settings.is_production and any(o.startswith("http://localhost") for o in settings.cors_origins):
        problems.append("CORS_ORIGINS still contains localhost in production")
    return problems
