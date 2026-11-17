"""Question generation orchestrator.

``generate_for_topic`` is the single entry point used by both the synchronous
API endpoint and the Celery task. It retrieves syllabus context (falling back
to a web search when the topic has no notes), asks the LLM for questions,
removes duplicates of earlier questions and stores the survivors.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GeneratedQuestion, SyllabusDocument, Topic
from app.services.dedup_service import filter_duplicates, question_hash
from app.services.generation_service import generate_mcqs, normalise_difficulty
from app.services.retrieval_service import retrieve_context
from app.services.web_search_service import persist_web_context, search_topic_context

logger = logging.getLogger(__name__)

MAX_COUNT = 25
WEB_SEARCH_RESULTS = 5
NO_CONTENT_MESSAGE = "No content for this topic — upload a PDF first"


class TopicNotFoundError(LookupError):
    """Raised when the topic does not exist (maps naturally to HTTP 404)."""


class NoContentError(LookupError):
    """Raised when there is no syllabus/web context to generate from (maps naturally to HTTP 422)."""


def _iso(value: datetime | None) -> str | None:
    """Serialise a datetime to ISO-8601 (or None) so results are JSON friendly."""
    return value.isoformat() if isinstance(value, datetime) else None


def question_to_dict(question: GeneratedQuestion) -> dict:
    """Convert a ``GeneratedQuestion`` row into a ``GeneratedQuestionRead``-shaped, JSON-serialisable dict."""
    return {
        "id": question.id,
        "topic_id": question.topic_id,
        "question_text": question.question_text,
        "options": list(question.options or []),
        "correct_index": question.correct_index,
        "explanation": question.explanation or "",
        "source": question.source,
        "difficulty": question.difficulty,
        "question_hash": question.question_hash,
        "created_at": _iso(getattr(question, "created_at", None)),
        "updated_at": _iso(getattr(question, "updated_at", None)),
    }


def load_prior_questions(db: Session, topic_id: int, limit: int | None = None) -> list[str]:
    """Return the text of the most recent ``limit`` questions of a topic (newest first)."""
    limit = limit if limit is not None and limit > 0 else settings.MAX_PRIOR_QUESTIONS
    stmt = (
        select(GeneratedQuestion.question_text)
        .where(GeneratedQuestion.topic_id == topic_id)
        .order_by(GeneratedQuestion.id.desc())
        .limit(limit)
    )
    return [text for text in db.scalars(stmt).all() if text]


def _existing_hashes(db: Session, topic_id: int, hashes: list[str]) -> set[str]:
    """Return the subset of ``hashes`` already stored for the topic (exact duplicate check)."""
    if not hashes:
        return set()
    stmt = select(GeneratedQuestion.question_hash).where(
        GeneratedQuestion.topic_id == topic_id,
        GeneratedQuestion.question_hash.in_(hashes),
    )
    return {value for value in db.scalars(stmt).all() if value}


def _web_fallback(db: Session, topic: Topic) -> list[dict]:
    """Search the web for the topic, persist the snippets and return them as context dicts."""
    chapter = getattr(topic, "chapter", None)
    chapter_name = getattr(chapter, "name", None) if chapter is not None else None
    course = getattr(chapter, "course", None) if chapter is not None else None
    course_name = getattr(course, "name", None) if course is not None else None

    logger.info("Topic %s has no stored context; falling back to web search", topic.id)
    snippets = search_topic_context(
        topic.name,
        chapter_name,
        course_name,
        max_results=WEB_SEARCH_RESULTS,
        detail=topic.description,
        exam_name=getattr(course, "exam_name", None),
    )
    if not snippets:
        logger.warning("Web search returned nothing for topic %s (%r)", topic.id, topic.name)
        return []

    try:
        stored = persist_web_context(topic.id, topic.chapter_id, snippets)
        logger.info("Stored %d web snippet(s) in the vector store for topic %s", stored, topic.id)
    except Exception as exc:  # noqa: BLE001 - generation can still proceed with in-memory snippets
        logger.warning("Could not persist web context for topic %s: %s", topic.id, exc)

    try:
        existing_stmt = select(SyllabusDocument.filename).where(
            SyllabusDocument.topic_id == topic.id,
            SyllabusDocument.source_type == "web_search",
        )
        existing = set(db.scalars(existing_stmt).all())
        for snippet in snippets:
            filename = f"web:{snippet.get('url', '')}"[:500]
            if filename in existing:
                continue
            db.add(
                SyllabusDocument(
                    topic_id=topic.id,
                    filename=filename,
                    source_type="web_search",
                    status="ready",
                    chunk_count=1,
                )
            )
            existing.add(filename)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - bookkeeping failure must not block generation
        db.rollback()
        logger.warning("Could not record web-search documents for topic %s: %s", topic.id, exc)

    return [
        {"text": snippet["text"], "page_number": None, "source_type": "web_search", "score": 0.0}
        for snippet in snippets
        if snippet.get("text")
    ]


def _context_source(context: list[dict]) -> str:
    """``"web_search"`` when every chunk came from the web, otherwise ``"notes"``."""
    if context and all(chunk.get("source_type") == "web_search" for chunk in context):
        return "web_search"
    return "notes"


def generate_for_topic(
    db: Session,
    topic_id: int,
    count: int = 10,
    difficulty: str = "medium",
    allow_web_fallback: bool = True,
    providers: tuple[str, ...] | None = None,
    _context: list[dict] | None = None,
) -> dict:
    """Generate, de-duplicate and store MCQs for a topic.

    Steps: load the topic (``TopicNotFoundError`` if missing) -> retrieve
    context from the vector store, optionally falling back to a web search
    (``NoContentError`` when nothing is available) -> load the last
    ``MAX_PRIOR_QUESTIONS`` questions -> call the LLM -> drop duplicates ->
    persist ``GeneratedQuestion`` rows.

    Returns a JSON-serialisable dict with keys ``topic_id``, ``questions``
    (list of ``GeneratedQuestionRead``-shaped dicts), ``source``, ``model``,
    ``context_source`` (``"notes"`` or ``"web_search"``), ``requested``,
    ``generated``, ``attempts`` and ``duplicates_removed``.
    Both ``TopicNotFoundError`` and ``NoContentError`` are ``LookupError``
    subclasses; ``GenerationError`` propagates from the generation service.
    """
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(f"Topic {topic_id} not found")

    requested = max(1, min(int(count), MAX_COUNT))
    if requested != count:
        logger.info("Clamped requested count %s to %d for topic %s", count, requested, topic_id)
    level = normalise_difficulty(difficulty)

    # 1. Context from the vector store, then optionally from the web.
    course = topic.chapter.course
    query = f"{topic.name}. {topic.description}" if topic.description else topic.name
    context = _context if _context is not None else retrieve_context(topic_id, query=query, chapter_id=topic.chapter_id)
    if not context and allow_web_fallback:
        context = _web_fallback(db, topic)
    if not context:
        raise NoContentError(NO_CONTENT_MESSAGE)
    context_source = _context_source(context)

    # 2. Previously generated questions (newest first) to avoid repeats.
    prior = load_prior_questions(db, topic_id, settings.MAX_PRIOR_QUESTIONS)

    # 3. Ask the LLM.
    result = generate_mcqs(
        topic.name,
        [chunk["text"] for chunk in context],
        prior,
        count=requested,
        difficulty=level,
        exam_name=course.exam_name or course.name,
        syllabus_scope=topic.description,
        providers=providers,
    )

    # 4. Drop near-duplicates of recent questions and exact duplicates of anything ever stored.
    candidates = filter_duplicates(result["questions"], prior)
    hashes = [question_hash(candidate["question"]) for candidate in candidates]
    already_stored = _existing_hashes(db, topic_id, hashes)
    unique: list[tuple[dict, str]] = [
        (candidate, digest) for candidate, digest in zip(candidates, hashes) if digest not in already_stored
    ]
    duplicates_removed = len(result["questions"]) - len(unique)
    if duplicates_removed:
        logger.info("Dropped %d duplicate question(s) for topic %s", duplicates_removed, topic_id)

    # 5. Persist.
    rows: list[GeneratedQuestion] = [
        GeneratedQuestion(
            topic_id=topic.id,
            question_text=candidate["question"],
            options=candidate["options"],
            correct_index=candidate["correct_index"],
            explanation=candidate.get("explanation", "") or "",
            source=candidate.get("source") or result["source"],
            # "mixed" runs keep the level the model assigned to each question.
            difficulty=level if level != "mixed" else (candidate.get("difficulty") or "medium"),
            question_hash=digest,
        )
        for candidate, digest in unique
    ]
    if rows:
        db.add_all(rows)
        db.commit()
        for row in rows:
            db.refresh(row)

    logger.info(
        "Stored %d/%d question(s) for topic %s from %s (%s, context=%s)",
        len(rows),
        requested,
        topic_id,
        result["source"],
        result["model"],
        context_source,
    )

    # The notes are "exhausted" for this topic when most new questions turn out to be
    # duplicates: research the web and write the remainder from what it finds.
    if (
        _context is None
        and allow_web_fallback
        and context_source == "notes"
        and requested >= 3
        and len(rows) < requested / 2
    ):
        logger.info("Notes exhausted for topic %s (%d/%d new); researching the web", topic_id, len(rows), requested)
        web = _web_fallback(db, topic)
        if web:
            more = generate_for_topic(
                db, topic_id, count=requested - len(rows), difficulty=difficulty,
                allow_web_fallback=False, providers=providers, _context=web,
            )
            extra = more["questions"]
            return {
                "topic_id": topic.id,
                "questions": [question_to_dict(row) for row in rows] + extra,
                "source": result["source"],
                "model": result["model"],
                "context_source": "notes+web_search",
                "requested": requested,
                "generated": len(rows) + len(extra),
                "attempts": result.get("attempts", 1) + more.get("attempts", 1),
                "duplicates_removed": duplicates_removed,
            }

    return {
        "topic_id": topic.id,
        "questions": [question_to_dict(row) for row in rows],
        "source": result["source"],
        "model": result["model"],
        "context_source": context_source,
        "requested": requested,
        "generated": len(rows),
        "attempts": result.get("attempts", 1),
        "duplicates_removed": duplicates_removed,
    }
