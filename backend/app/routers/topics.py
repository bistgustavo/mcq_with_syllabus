"""Topics: CRUD, syllabus uploads, ingestion status, question generation and quiz start."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Chapter, Course, GeneratedQuestion, SyllabusDocument, Topic, User
from app.models.syllabus_document import DOC_PENDING, DOC_PROCESSING
from app.schemas.generated_question import (
    AsyncTaskAccepted,
    GeneratedQuestionRead,
    GenerateQuestionsRequest,
    GenerationResponse,
    QuestionHistory,
    validate_difficulty,
)
from app.schemas.quiz_attempt import QuizStart, TopicStats
from app.schemas.syllabus_document import SyllabusDocumentRead, UploadResponse
from app.schemas.topic import TopicCreate, TopicDetail, TopicRead, TopicStatus, TopicUpdate
from app.services.attempt_service import last_seen, pick_questions, topic_stats, unseen_count
from app.services.generation_service import GenerationError
from app.services.quiz_service import NoContentError, TopicNotFoundError, generate_for_topic
from app.services.retrieval_service import topic_chunk_count
from app.utils.cleanup import delete_topics, purge_document_artifacts, purge_topic_artifacts, topic_upload_dir
from app.utils.security import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])

PDF_MAGIC = b"%PDF-"


def _get_topic(db: Session, topic_id: int, user: User | None = None) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    if user is not None and not user.is_admin:
        course = topic.chapter.course
        if not course.is_published:
            raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    return topic


# --------------------------------------------------------------------------- CRUD
@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
def create_topic(payload: TopicCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Topic:
    if db.get(Chapter, payload.chapter_id) is None:
        raise HTTPException(status_code=404, detail=f"Chapter {payload.chapter_id} not found")
    topic = Topic(chapter_id=payload.chapter_id, name=payload.name.strip(), description=payload.description)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


@router.get("/{topic_id}", response_model=TopicDetail)
def get_topic(topic_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    topic = _get_topic(db, topic_id, user)
    chapter: Chapter = topic.chapter
    course: Course = chapter.course
    by_difficulty = dict(
        db.execute(
            select(GeneratedQuestion.difficulty, func.count(GeneratedQuestion.id))
            .where(GeneratedQuestion.topic_id == topic_id)
            .group_by(GeneratedQuestion.difficulty)
        ).all()
    )
    return {
        **TopicRead.model_validate(topic).model_dump(),
        "chapter_name": chapter.name,
        "course_id": course.id,
        "course_name": course.name,
        "question_count": int(sum(by_difficulty.values())),
        "question_count_by_difficulty": {str(k): int(v) for k, v in by_difficulty.items()},
    }


@router.patch("/{topic_id}", response_model=TopicRead)
def update_topic(
    topic_id: int, payload: TopicUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> Topic:
    topic = _get_topic(db, topic_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        topic.name = data["name"].strip()
    if "description" in data:
        topic.description = data["description"]
    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_topic(topic_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Response:
    _get_topic(db, topic_id)
    delete_topics(db, [topic_id])
    db.commit()
    purge_topic_artifacts([topic_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- content
@router.get("/{topic_id}/status", response_model=TopicStatus)
def topic_status(topic_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    topic = _get_topic(db, topic_id, user)
    from sqlalchemy import or_

    docs = db.scalars(
        select(SyllabusDocument)
        .where(or_(SyllabusDocument.topic_id == topic_id, SyllabusDocument.chapter_id == topic.chapter_id))
        .order_by(SyllabusDocument.id.desc())
    ).all()
    question_count = db.scalar(select(func.count(GeneratedQuestion.id)).where(GeneratedQuestion.topic_id == topic_id))
    return {
        "topic_id": topic_id,
        "has_content": topic.has_content,
        "has_web_content": any(d.source_type == "web_search" for d in docs),
        "processing": any(d.status in (DOC_PENDING, DOC_PROCESSING) for d in docs),
        "chunk_count": topic_chunk_count(topic_id, topic.chapter_id),
        "question_count": int(question_count or 0),
        "documents": [SyllabusDocumentRead.model_validate(d) for d in docs],
    }


@router.post("/{topic_id}/upload-syllabus", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_syllabus(
    topic_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Store a PDF for the topic and queue background ingestion."""
    from app.workers.ingestion_worker import ingest_pdf_task  # lazy: keeps API import light

    topic = _get_topic(db, topic_id)
    original = (file.filename or "").strip()
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    head = file.file.read(len(PDF_MAGIC))
    if head != PDF_MAGIC:
        raise HTTPException(status_code=400, detail="The file is not a valid PDF")
    file.file.seek(0)

    folder = topic_upload_dir(topic_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    dest = folder / stored_name

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise

    safe_display = original.replace("/", "_").replace("\\", "_")[:500]
    doc = SyllabusDocument(
        topic_id=topic_id,
        filename=safe_display,
        stored_filename=stored_name,
        source_type="upload",
        status=DOC_PENDING,
        file_size=written,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        task = ingest_pdf_task.delay(
            topic_id=topic_id,
            chapter_id=topic.chapter_id,
            file_path=str(dest),
            syllabus_document_id=doc.id,
        )
    except Exception as exc:  # broker unreachable
        logger.error("Could not queue ingestion for document %s: %s", doc.id, exc)
        doc.status = "failed"
        doc.error = "Task queue unavailable — is Redis reachable and the worker running?"
        db.commit()
        raise HTTPException(status_code=503, detail=doc.error) from exc

    doc.task_id = task.id
    db.commit()
    db.refresh(doc)
    return {"message": "File uploaded. Ingestion started.", "task_id": task.id, "document": doc}


@router.post("/{topic_id}/documents/{document_id}/reingest", response_model=UploadResponse, status_code=202)
def reingest_document(
    topic_id: int, document_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> dict:
    from app.workers.ingestion_worker import ingest_pdf_task

    topic = _get_topic(db, topic_id)
    doc = db.get(SyllabusDocument, document_id)
    if doc is None or doc.topic_id != topic_id or not doc.stored_filename:
        raise HTTPException(status_code=404, detail="Uploaded document not found")
    path = topic_upload_dir(topic_id) / doc.stored_filename
    if not path.is_file():
        raise HTTPException(status_code=410, detail="The original file is no longer on disk; upload it again")
    task = ingest_pdf_task.delay(
        topic_id=topic_id, chapter_id=topic.chapter_id, file_path=str(path), syllabus_document_id=doc.id
    )
    doc.status = DOC_PENDING
    doc.error = None
    doc.task_id = task.id
    db.commit()
    db.refresh(doc)
    return {"message": "Re-ingestion started.", "task_id": task.id, "document": doc}


@router.delete("/{topic_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    topic_id: int, document_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> Response:
    from app.workers.ingestion_worker import refresh_topic_has_content

    doc = db.get(SyllabusDocument, document_id)
    if doc is None or doc.topic_id != topic_id:
        raise HTTPException(status_code=404, detail="Document not found")
    purge_document_artifacts(doc)
    db.delete(doc)
    db.flush()
    refresh_topic_has_content(db, topic_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- generation
@router.post(
    "/{topic_id}/generate-questions",
    response_model=GenerationResponse,
    responses={202: {"model": AsyncTaskAccepted}},
)
def generate_questions(
    topic_id: int,
    payload: GenerateQuestionsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Generate fresh MCQs (admin only: it spends LLM quota). ``run_async`` queues a Celery task."""
    _get_topic(db, topic_id, user)

    if payload.run_async:
        from app.workers.generation_worker import generate_questions_task

        try:
            task = generate_questions_task.delay(
                topic_id=topic_id,
                count=payload.count,
                difficulty=payload.difficulty,
                allow_web_fallback=payload.use_web_fallback,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Task queue unavailable") from exc
        body = AsyncTaskAccepted(task_id=task.id, topic_id=topic_id, message="Generation queued")
        return JSONResponse(status_code=202, content=body.model_dump())

    try:
        return generate_for_topic(
            db,
            topic_id=topic_id,
            count=payload.count,
            difficulty=payload.difficulty,
            allow_web_fallback=payload.use_web_fallback,
        )
    except TopicNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{topic_id}/questions", response_model=QuestionHistory)
def list_questions(
    topic_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    difficulty: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Question bank for a topic (with answers) — admin only."""
    _get_topic(db, topic_id)
    base = select(GeneratedQuestion).where(GeneratedQuestion.topic_id == topic_id)
    count_stmt = select(func.count(GeneratedQuestion.id)).where(GeneratedQuestion.topic_id == topic_id)
    if difficulty:
        level = validate_difficulty(difficulty)
        base = base.where(GeneratedQuestion.difficulty == level)
        count_stmt = count_stmt.where(GeneratedQuestion.difficulty == level)
    items = db.scalars(base.order_by(GeneratedQuestion.id.desc()).limit(limit).offset(offset)).all()
    return {
        "total": int(db.scalar(count_stmt) or 0),
        "limit": limit,
        "offset": offset,
        "items": [GeneratedQuestionRead.model_validate(q) for q in items],
    }


@router.delete("/{topic_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    topic_id: int, question_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> Response:
    question = db.get(GeneratedQuestion, question_id)
    if question is None or question.topic_id != topic_id:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{topic_id}/stats", response_model=TopicStats)
def get_topic_stats(topic_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    _get_topic(db, topic_id, user)
    return topic_stats(db, topic_id)


# --------------------------------------------------------------------------- quiz
@router.get("/{topic_id}/quiz", response_model=QuizStart)
def start_quiz(
    topic_id: int,
    count: int = Query(10, ge=1, le=50),
    difficulty: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Serve ``count`` questions (answers withheld): unseen first, then the least recently seen.

    When the student is short of unseen questions, fresh ones are written on the
    spot from the topic's notes with the fast cloud models; if those are busy or
    rate-limited, a background top-up is queued and a few old questions repeat.
    """
    from app.services.generation_service import CLOUD_PROVIDERS
    from app.workers.research_worker import queue_top_up

    topic = _get_topic(db, topic_id, user)
    level = validate_difficulty(difficulty) if difficulty else None
    fresh = 0
    shortage = count - unseen_count(db, user, topic_id, level)
    if shortage > 0:
        if settings.GROQ_API_KEY or settings.GEMINI_API_KEY:
            try:
                result = generate_for_topic(
                    db, topic_id=topic_id, count=min(max(shortage, 5), 10), difficulty=level or "mixed",
                    providers=CLOUD_PROVIDERS,
                )
                fresh = result["generated"]
            except Exception as exc:  # noqa: BLE001 - never block practice on generation
                db.rollback()
                logger.info("Instant generation unavailable for topic %s: %s", topic_id, exc)
        if fresh < shortage:
            queue_top_up([topic_id])
    questions = pick_questions(db, user, topic_id, count, level)
    seen = last_seen(db, user)
    return {
        "topic_id": topic_id,
        "topic_name": topic.name,
        "difficulty": level,
        "requested": count,
        "available": len(questions),
        "fresh_generated": fresh,
        "repeats": sum(1 for q in questions if q.id in seen),
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "options": list(q.options or []),
                "difficulty": q.difficulty,
                "source": q.source,
            }
            for q in questions
        ],
    }
