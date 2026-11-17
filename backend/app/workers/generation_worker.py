"""Celery task that generates MCQs for a topic in the background."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.services.generation_service import GenerationError
from app.services.quiz_service import generate_for_topic
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_questions", max_retries=1, default_retry_delay=20)
def generate_questions_task(
    self, topic_id: int, count: int, difficulty: str, allow_web_fallback: bool = True
) -> dict:
    """Generate and store questions for ``topic_id`` using ``quiz_service.generate_for_topic``.

    Returns the same JSON-serialisable dict as the synchronous endpoint. A
    ``GenerationError`` (every LLM provider failed) is retried once after
    ``default_retry_delay`` seconds; a ``LookupError`` (unknown topic or no
    content) fails immediately because retrying cannot help.
    """
    logger.info(
        "generate_questions task %s started: topic=%s count=%s difficulty=%s",
        self.request.id,
        topic_id,
        count,
        difficulty,
    )
    db = SessionLocal()
    try:
        result = generate_for_topic(
            db,
            topic_id=topic_id,
            count=count,
            difficulty=difficulty,
            allow_web_fallback=allow_web_fallback,
        )
        logger.info(
            "generate_questions task %s finished: %s/%s question(s) stored for topic %s",
            self.request.id,
            result.get("generated"),
            result.get("requested"),
            topic_id,
        )
        return result
    except LookupError as exc:
        logger.warning("generate_questions task %s failed permanently: %s", self.request.id, exc)
        raise
    except GenerationError as exc:
        logger.warning("generate_questions task %s: generation failed (%s); scheduling retry", self.request.id, exc)
        raise self.retry(exc=exc)
    except Exception:
        logger.exception("generate_questions task %s crashed for topic %s", self.request.id, topic_id)
        raise
    finally:
        db.close()
