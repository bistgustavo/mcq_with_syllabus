"""Cascade-deletion helpers for courses, chapters, topics and documents.

Deletes bottom-up with bulk statements (works the same on MySQL and SQLite,
regardless of FK cascade support) and then, best-effort, purges Qdrant points
and uploaded files. DB helpers flush but never commit; call
``purge_topic_artifacts`` only after the transaction has been committed.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chapter, Course, ExamAttempt, GeneratedQuestion, PastPaper, QuizAttempt, SyllabusDocument, Topic
from app.vector_db import delete_points

logger = logging.getLogger(__name__)


def upload_root() -> Path:
    """Absolute directory where uploaded PDFs are stored."""
    return Path(settings.UPLOAD_DIR).resolve()


def topic_upload_dir(topic_id: int) -> Path:
    return upload_root() / str(int(topic_id))


def delete_topics(db: Session, topic_ids: Sequence[int]) -> int:
    """Delete topics and every row referencing them. Returns the number deleted."""
    ids = [int(i) for i in topic_ids]
    if not ids:
        return 0
    db.execute(delete(QuizAttempt).where(QuizAttempt.topic_id.in_(ids)))
    db.execute(delete(GeneratedQuestion).where(GeneratedQuestion.topic_id.in_(ids)))
    db.execute(delete(SyllabusDocument).where(SyllabusDocument.topic_id.in_(ids)))
    result = db.execute(delete(Topic).where(Topic.id.in_(ids)))
    db.expire_all()
    return int(result.rowcount or 0)


def delete_chapters(db: Session, chapter_ids: Sequence[int]) -> list[int]:
    """Delete chapters plus their topics. Returns the removed topic ids."""
    ids = [int(i) for i in chapter_ids]
    if not ids:
        return []
    topic_ids = [int(t) for t in db.scalars(select(Topic.id).where(Topic.chapter_id.in_(ids))).all()]
    delete_topics(db, topic_ids)
    db.execute(delete(SyllabusDocument).where(SyllabusDocument.chapter_id.in_(ids)))
    for chapter_id in ids:  # chapter-wide notes in the vector store (best effort)
        try:
            delete_points("chapter_id", chapter_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not purge Qdrant points for chapter %s: %s", chapter_id, exc)
    db.execute(delete(Chapter).where(Chapter.id.in_(ids)))
    db.expire_all()
    return topic_ids


def delete_course(db: Session, course_id: int) -> list[int]:
    """Delete a course with all chapters/topics. Returns the removed topic ids."""
    chapter_ids = [int(c) for c in db.scalars(select(Chapter.id).where(Chapter.course_id == course_id)).all()]
    topic_ids = delete_chapters(db, chapter_ids)
    db.execute(delete(ExamAttempt).where(ExamAttempt.course_id == course_id))
    db.execute(delete(PastPaper).where(PastPaper.course_id == course_id))
    db.execute(delete(Course).where(Course.id == course_id))
    db.expire_all()
    return topic_ids


def purge_topic_artifacts(topic_ids: Sequence[int]) -> None:
    """Best-effort removal of Qdrant points and uploaded PDFs. Never raises."""
    for topic_id in topic_ids:
        try:
            delete_points("topic_id", int(topic_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not purge Qdrant points for topic %s: %s", topic_id, exc)
        folder = topic_upload_dir(topic_id)
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


def purge_document_artifacts(document: SyllabusDocument) -> None:
    """Best-effort removal of one document's Qdrant points and file. Never raises."""
    try:
        delete_points("document_id", int(document.id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not purge Qdrant points for document %s: %s", document.id, exc)
    if document.stored_filename:
        folder = topic_upload_dir(document.topic_id) if document.topic_id else upload_root() / f"chapter-{document.chapter_id}"
        path = folder / document.stored_filename
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path, exc)
