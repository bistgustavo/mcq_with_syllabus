"""Cloud-first, local-fallback resolution of Qdrant and Redis endpoints.

Each process probes the cloud endpoint once at startup (short timeouts). If it
answers, the cloud is used; otherwise the local endpoint is used. The choice is
cached per process and exposed through ``active_endpoints()`` for the health
page. Set ``*_LOCAL_URL`` to an empty string to disable the fallback.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import httpx
import redis

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Endpoint:
    url: str
    api_key: str
    mode: str  # "cloud" | "local"
    note: str = ""


_lock = threading.Lock()
_qdrant: Endpoint | None = None
_redis: Endpoint | None = None


def _qdrant_ok(url: str, api_key: str) -> tuple[bool, str]:
    try:
        headers = {"api-key": api_key} if api_key else {}
        r = httpx.get(f"{url.rstrip('/')}/collections", headers=headers, timeout=4.0)
        if r.status_code == 200:
            return True, ""
        return False, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]


def _redis_ok(url: str) -> tuple[bool, str]:
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        client.close()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]


def qdrant_endpoint() -> Endpoint:
    """The Qdrant endpoint this process uses (resolved once)."""
    global _qdrant
    if _qdrant is None:
        with _lock:
            if _qdrant is None:
                primary = settings.QDRANT_URL.strip()
                local = settings.QDRANT_LOCAL_URL.strip()
                if not local or local == primary:
                    _qdrant = Endpoint(primary, settings.QDRANT_API_KEY, "cloud" if "cloud" in primary else "local")
                else:
                    ok, why = _qdrant_ok(primary, settings.QDRANT_API_KEY)
                    if ok:
                        _qdrant = Endpoint(primary, settings.QDRANT_API_KEY, "cloud")
                    else:
                        logger.warning("Cloud Qdrant unavailable (%s); using local %s", why, local)
                        _qdrant = Endpoint(local, "", "local", f"cloud unavailable: {why}")
    return _qdrant


def redis_endpoint() -> Endpoint:
    """The Redis URL this process uses (resolved once). Also the Celery broker."""
    global _redis
    if _redis is None:
        with _lock:
            if _redis is None:
                primary = settings.REDIS_URL.strip()
                local = settings.REDIS_LOCAL_URL.strip()
                if not local or local == primary:
                    _redis = Endpoint(primary, "", "cloud" if "localhost" not in primary else "local")
                else:
                    ok, why = _redis_ok(primary)
                    if ok:
                        _redis = Endpoint(primary, "", "cloud")
                    else:
                        logger.warning("Cloud Redis unavailable (%s); using local %s", why, local)
                        _redis = Endpoint(local, "", "local", f"cloud unavailable: {why}")
    return _redis


def active_endpoints() -> dict:
    q, r = qdrant_endpoint(), redis_endpoint()
    return {"qdrant": {"mode": q.mode, "note": q.note}, "redis": {"mode": r.mode, "note": r.note}}
