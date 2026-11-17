"""
Celery ingestion task: PDF → text chunks → embeddings → Qdrant → MySQL status.

The document row tracks progress (pending → processing → ready/empty/failed),
so the UI can show live status. Point IDs are deterministic per document, so a
retry overwrites rather than duplicates. Errors that cannot be fixed by
retrying (missing/corrupt file, unknown document) fail immediately.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.syllabus_document import (
    DOC_EMPTY,
    DOC_FAILED,
    DOC_PROCESSING,
    DOC_READY,
    SyllabusDocument,
)
from app.models.topic import Topic
from app.services.embedding_service import embed_batch
from app.services.ingestion_service import count_pages, extract_and_chunk
from app.vector_db import delete_points, upsert_chunks
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class PermanentIngestionError(Exception):
    """Raised for failures that a retry cannot fix."""


def _set_status(document_id: int, status: str, **fields) -> None:
    db = SessionLocal()
    try:
        doc = db.get(SyllabusDocument, document_id)
        if doc is None:
            return
        doc.status = status
        for key, value in fields.items():
            setattr(doc, key, value)
        db.commit()
    finally:
        db.close()


def refresh_topic_has_content(db, topic_id: int) -> None:
    """has_content = a ready document with chunks exists for the topic or for its whole chapter."""
    from sqlalchemy import or_

    topic = db.get(Topic, topic_id)
    if topic is None:
        return
    ready = db.scalar(
        select(func.count(SyllabusDocument.id)).where(
            or_(SyllabusDocument.topic_id == topic_id, SyllabusDocument.chapter_id == topic.chapter_id),
            SyllabusDocument.status == DOC_READY,
            SyllabusDocument.chunk_count > 0,
        )
    )
    topic.has_content = bool(ready)


def refresh_chapter_has_content(db, chapter_id: int) -> None:
    for topic_id in db.scalars(select(Topic.id).where(Topic.chapter_id == chapter_id)).all():
        refresh_topic_has_content(db, topic_id)


@celery_app.task(bind=True, name="ingest_pdf", max_retries=3, default_retry_delay=30)
def ingest_pdf_task(
    self,
    topic_id: int | None,
    chapter_id: int,
    file_path: str,
    syllabus_document_id: int,
) -> dict:
    """Ingest a PDF for one topic, or for a whole chapter when ``topic_id`` is None."""
    """Run the full ingestion pipeline for a single uploaded PDF."""
    logger.info("Ingesting document %s (topic %s) from %s", syllabus_document_id, topic_id, file_path)
    _set_status(syllabus_document_id, DOC_PROCESSING, error=None)

    try:
        try:
            chunks = extract_and_chunk(file_path)
        except FileNotFoundError as exc:
            raise PermanentIngestionError(f"Uploaded file is missing: {exc}") from exc
        except Exception as exc:  # pdfplumber raises many types for corrupt files
            raise PermanentIngestionError(f"Could not read PDF: {exc}") from exc

        page_count = count_pages(file_path)
        if not chunks:
            _set_status(
                syllabus_document_id,
                DOC_EMPTY,
                chunk_count=0,
                page_count=page_count,
                error="No extractable text found (is this a scanned PDF?)",
            )
            return {"status": DOC_EMPTY, "chunks": 0, "topic_id": topic_id, "document_id": syllabus_document_id}

        texts = [c["text"] for c in chunks]
        page_numbers = [c["page_number"] for c in chunks]
        vectors = embed_batch(texts)

        # Remove stale points of this document (e.g. a previous partial run).
        delete_points("document_id", syllabus_document_id)
        stored = upsert_chunks(
            vectors=vectors,
            texts=texts,
            topic_id=topic_id,
            chapter_id=chapter_id,
            source_type="upload",
            page_numbers=page_numbers,
            document_id=syllabus_document_id,
        )

        db = SessionLocal()
        try:
            doc = db.get(SyllabusDocument, syllabus_document_id)
            if doc is not None:
                doc.status = DOC_READY
                doc.chunk_count = stored
                doc.page_count = page_count
                doc.error = None
            db.flush()
            if topic_id is None:
                refresh_chapter_has_content(db, chapter_id)
            else:
                refresh_topic_has_content(db, topic_id)
            db.commit()
        finally:
            db.close()

        result = {"status": DOC_READY, "chunks": stored, "pages": page_count, "topic_id": topic_id,
                  "document_id": syllabus_document_id}
        logger.info("Ingestion complete: %s", result)
        return result

    except PermanentIngestionError as exc:
        logger.warning("Ingestion of document %s failed permanently: %s", syllabus_document_id, exc)
        _set_status(syllabus_document_id, DOC_FAILED, error=str(exc)[:2000])
        raise
    except Exception as exc:
        logger.exception("Ingestion of document %s failed", syllabus_document_id)
        if self.request.retries >= self.max_retries:
            _set_status(syllabus_document_id, DOC_FAILED, error=f"{type(exc).__name__}: {exc}"[:2000])
            raise
        raise self.retry(exc=exc)
