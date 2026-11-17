"""Expose Celery task state through the HTTP API in one consistent shape."""

import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import HTTPException, status

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def task_status_payload(task_id: str) -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of a Celery task.

    Shape: ``{"task_id", "state", "result", "error"}``. ``result`` is the task's
    return value only when it finished successfully; ``error`` is the stringified
    exception only when it failed; otherwise both are ``None``. Unknown ids show
    up as ``PENDING`` (Celery semantics). Raises HTTP 503 when the result backend
    (Redis) cannot be reached.
    """
    try:
        res = AsyncResult(task_id, app=celery_app)
        state = res.state
        result = res.result if res.successful() else None
        error = str(res.result) if res.failed() else None
        # In-flight progress (e.g. the course pipeline reports done/total).
        progress = res.info if state == "PROGRESS" and isinstance(res.info, dict) else None
    except Exception as exc:  # backend/network failures must surface as 503, not 500
        logger.error("Unable to read state of Celery task %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task result backend is unavailable",
        ) from exc
    return {"task_id": task_id, "state": state, "result": result, "error": error, "progress": progress}
