"""Shared Redis connection (LLM circuit breaker + health checks).

The client is created lazily so importing this module never opens a socket;
connection errors surface on first use and callers treat Redis as optional.
"""

from __future__ import annotations

from functools import lru_cache

import redis



@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """Return the process-wide Redis client."""
    from app.infra import redis_endpoint

    return redis.Redis.from_url(
        redis_endpoint().url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )


class _LazyRedis:
    """Proxy so ``from app.redis_client import redis_client`` keeps working."""

    def __getattr__(self, name: str):
        return getattr(get_redis(), name)


redis_client = _LazyRedis()
