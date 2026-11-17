"""FastAPI application entry point."""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, courses, exams, quiz, topics
from app.utils import hardening

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

_log = logging.getLogger("app")
_problems = hardening.validate_settings()
for _p in _problems:
    _log.warning("Configuration problem: %s", _p)
if _problems and settings.is_production:
    raise RuntimeError("Refusing to start in production: " + "; ".join(_problems))

app = FastAPI(
    title="QuizForge API",
    version="2.0.0",
    description="Syllabus-grounded MCQ generation, practice quizzes and timed mock exams.",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)
hardening.install(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(topics.router)
app.include_router(quiz.router)
app.include_router(exams.router)


@app.get("/api/v1/health", tags=["health"])
def health_check() -> dict:
    """Liveness probe: the process is up."""
    return {"status": "ok", "service": "mcq-platform-backend"}


def _probe(fn) -> dict:
    started = time.monotonic()
    try:
        detail = fn()
        return {"ok": True, "ms": round((time.monotonic() - started) * 1000), **(detail or {})}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ms": round((time.monotonic() - started) * 1000), "error": f"{type(exc).__name__}: {exc}"[:300]}


@app.get("/api/v1/health/deep", tags=["health"])
def deep_health() -> dict:
    """Readiness probe: checks every dependency the platform uses."""

    def database():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def redis_check():
        from app.redis_client import get_redis

        get_redis().ping()

    def qdrant():
        from app.vector_db import COLLECTION_NAME, get_client

        return {"collection_exists": get_client().collection_exists(COLLECTION_NAME)}

    def ollama():
        resp = httpx.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m.get("name") for m in resp.json().get("models", [])]
        return {"model": settings.OLLAMA_MODEL, "model_available": settings.OLLAMA_MODEL in models}

    def workers():
        from app.redis_client import get_redis

        beats = list(get_redis().scan_iter("worker:heartbeat:*", count=100))
        if beats:
            return {"count": len(beats)}
        from app.workers.celery_app import celery_app

        replies = celery_app.control.ping(timeout=1.5) or []
        if not replies:
            raise RuntimeError("no background worker is running")
        return {"count": len(replies)}

    from app.infra import active_endpoints

    endpoints = _probe(active_endpoints)
    checks = {
        "database": _probe(database),
        "redis": _probe(redis_check),
        "qdrant": _probe(qdrant),
        "ollama": _probe(ollama),
        "worker": _probe(workers),
        "groq": {"ok": bool(settings.GROQ_API_KEY), "configured": bool(settings.GROQ_API_KEY)},
        "gemini": {"ok": bool(settings.GEMINI_API_KEY), "configured": bool(settings.GEMINI_API_KEY)},
    }
    core = ("database", "redis", "qdrant", "worker")
    llm_ok = checks["ollama"]["ok"] or checks["groq"]["ok"] or checks["gemini"]["ok"]
    overall = "ok" if all(checks[c]["ok"] for c in core) and llm_ok else "degraded"
    llm_order = settings.provider_order
    return {"status": overall, "checks": checks, "infrastructure": endpoints, "llm_order": llm_order}
