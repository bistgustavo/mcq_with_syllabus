"""Background content pipeline.

* ``research_topic`` — web-search a topic using its syllabus detail and store
  the cleaned text as ``web_search`` context (Qdrant + document rows).
* ``build_course_bank`` — for every topic of a course: research it when it has
  no notes, then top its question bank up to a target, spread over
  easy/medium/hard. Progress is reported through the task state (PROGRESS) so
  the admin UI can show a live progress bar.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Chapter, Course, GeneratedQuestion, SyllabusDocument, Topic
from app.services.generation_service import GenerationError, patient
from app.services.quiz_service import NoContentError, generate_for_topic
from app.services.web_search_service import persist_web_context, search_topic_context
from app.workers.celery_app import celery_app
from app.workers.ingestion_worker import refresh_topic_has_content

logger = logging.getLogger(__name__)

RESEARCH_RESULTS = 6
LEVELS = ("easy", "medium", "hard")


def research_topic_now(db, topic: Topic) -> dict:
    """Search the web for ``topic`` and store what was found. Returns a summary."""
    chapter = topic.chapter
    course = chapter.course
    snippets = search_topic_context(
        topic.name,
        chapter.name,
        course.name,
        max_results=RESEARCH_RESULTS,
        detail=topic.description,
        exam_name=course.exam_name,
    )
    if not snippets:
        return {"topic_id": topic.id, "sources": 0, "stored": 0}

    stored = persist_web_context(topic.id, topic.chapter_id, snippets)
    existing = set(
        db.scalars(
            select(SyllabusDocument.filename).where(
                SyllabusDocument.topic_id == topic.id, SyllabusDocument.source_type == "web_search"
            )
        ).all()
    )
    for snippet in snippets:
        name = f"web:{snippet.get('url', '')}"[:500]
        if name in existing:
            continue
        db.add(
            SyllabusDocument(
                topic_id=topic.id, filename=name, source_type="web_search", status="ready", chunk_count=1
            )
        )
        existing.add(name)
    db.flush()
    refresh_topic_has_content(db, topic.id)
    db.commit()
    return {"topic_id": topic.id, "sources": len(snippets), "stored": stored}


@celery_app.task(bind=True, name="research_topic", max_retries=1, default_retry_delay=30)
def research_topic_task(self, topic_id: int) -> dict:
    db = SessionLocal()
    try:
        topic = db.get(Topic, topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")
        result = research_topic_now(db, topic)
        if not result["sources"]:
            raise RuntimeError("Web search returned no usable pages for this topic")
        return result
    finally:
        db.close()


def _question_counts(db, topic_id: int) -> dict[str, int]:
    rows = db.execute(
        select(GeneratedQuestion.difficulty, func.count(GeneratedQuestion.id))
        .where(GeneratedQuestion.topic_id == topic_id)
        .group_by(GeneratedQuestion.difficulty)
    ).all()
    return {str(k): int(v) for k, v in rows}


def queue_top_up(topic_ids: list[int], count: int = 6) -> bool:
    """Best-effort: queue background generation for topics that are running low."""
    if not topic_ids:
        return False
    try:
        from app.redis_client import get_redis

        get_redis().ping()  # fail fast (3 s) instead of hanging on an unreachable broker
        top_up_topics_task.apply_async(kwargs={"topic_ids": list(topic_ids)[:40], "count": count}, retry=False)
        return True
    except Exception as exc:  # noqa: BLE001 - queue down: the student just sees a few repeats
        logger.warning("Could not queue top-up for %d topic(s): %s", len(topic_ids), exc)
        return False


@celery_app.task(bind=True, name="top_up_topics")
def top_up_topics_task(self, topic_ids: list[int], count: int = 6) -> dict:
    """Write fresh questions (mixed difficulty) for topics whose unseen stock is low."""
    with patient():
        return _top_up(topic_ids, count)


def _top_up(topic_ids: list[int], count: int) -> dict:
    db = SessionLocal()
    added = 0
    try:
        for topic_id in topic_ids:
            try:
                added += generate_for_topic(db, topic_id=topic_id, count=count, difficulty="mixed")["generated"]
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.warning("Top-up failed for topic %s: %s", topic_id, exc)
        return {"topics": len(topic_ids), "generated": added}
    finally:
        db.close()


@celery_app.task(bind=True, name="find_past_papers")
def find_past_papers_task(self, course_id: int) -> dict:
    """Search PSC, NRB and the web for past papers, list them, then read each one."""
    with patient():
        return _find_papers(self, course_id)


def _find_papers(self, course_id: int) -> dict:
    from app.models import PastPaper
    from app.models.past_paper import PAPER_FAILED, PAPER_FOUND, PAPER_PROCESSING
    from app.services.paper_finder import discover, process_paper, save_candidates

    db = SessionLocal()
    try:
        course = db.get(Course, course_id)
        if course is None:
            raise LookupError(f"Course {course_id} not found")
        db.rollback()
        self.update_state(state="PROGRESS", meta={"phase": "searching", "current": "Searching PSC, NRB and the web…"})
        candidates = discover(course)  # network only, no open transaction
        new = save_candidates(db, course_id, candidates)
        todo = list(db.scalars(
            # "processing" here is stale (a previous worker died mid-paper): only one search runs per course.
            select(PastPaper.id).where(
                PastPaper.course_id == course_id,
                PastPaper.status.in_([PAPER_FOUND, PAPER_FAILED, PAPER_PROCESSING]),
            )
            .order_by(PastPaper.id)
        ).all())
        db.rollback()
    finally:
        db.close()

    summary = {"found": len(candidates), "new": new, "processed": 0, "mcq_added": 0}
    for n, paper_id in enumerate(todo):
        self.update_state(state="PROGRESS", meta={"phase": "reading", "done": n, "total": len(todo),
                                                  "current": f"Reading paper {n + 1} of {len(todo)}", **summary})
        result = process_paper(SessionLocal, paper_id)
        summary["processed"] += 1
        summary["mcq_added"] += int(result.get("added") or 0)
    return summary


@celery_app.task(bind=True, name="process_past_paper")
def process_past_paper_task(self, paper_id: int) -> dict:
    from app.services.paper_finder import process_paper

    with patient():
        return process_paper(SessionLocal, paper_id)


@celery_app.task(bind=True, name="import_past_paper")
def import_past_paper_task(self, course_id: int, file_path: str, label: str, paper: str | None = None) -> dict:
    """OCR/read an uploaded past paper and add its MCQs to the course bank."""
    from pathlib import Path

    from app.services.past_paper_service import import_past_paper

    db = SessionLocal()
    try:
        course = db.get(Course, course_id)
        if course is None:
            raise LookupError(f"Course {course_id} not found")
        self.update_state(state="PROGRESS", meta={"current": "Reading the paper (OCR if scanned)…"})
        result = import_past_paper(db, course, Path(file_path), label, paper)
        logger.info("Past paper %r for course %s: %s", label, course_id, result)
        return result
    finally:
        db.close()


@celery_app.task(bind=True, name="collect_online_questions")
def collect_online_questions_task(self, course_id: int, max_pages: int = 12) -> dict:
    """Search the web for old questions of the course's exam and import the MCQs found."""
    from app.services.past_paper_service import collect_online

    db = SessionLocal()
    try:
        course = db.get(Course, course_id)
        if course is None:
            raise LookupError(f"Course {course_id} not found")

        def progress(done, total, title):
            self.update_state(state="PROGRESS", meta={"done": done, "total": total, "current": str(title)[:120]})

        return collect_online(db, course, max_pages=max_pages, progress=progress)
    finally:
        db.close()


@celery_app.task(bind=True, name="build_course_bank")
def build_course_bank_task(self, course_id: int, per_topic: int = 15, research: bool = True) -> dict:
    """Research missing content and fill each topic's bank up to ``per_topic`` questions."""
    with patient():
        return _build_bank(self, course_id, per_topic, research)


def _build_bank(self, course_id: int, per_topic: int, research: bool) -> dict:
    db = SessionLocal()
    log: list[str] = []
    summary = {"topics": 0, "researched": 0, "generated": 0, "failed": 0}
    try:
        course = db.get(Course, course_id)
        if course is None:
            raise LookupError(f"Course {course_id} not found")
        topics = db.scalars(
            select(Topic)
            .join(Chapter, Chapter.id == Topic.chapter_id)
            .where(Chapter.course_id == course_id)
            .order_by(Chapter.order, Chapter.id, Topic.id)
        ).all()
        summary["topics"] = len(topics)

        def report(index: int, current: str) -> None:
            self.update_state(
                state="PROGRESS",
                meta={"done": index, "total": len(topics), "current": current, "log": log[-30:], **summary},
            )

        for index, topic in enumerate(topics):
            report(index, topic.name)
            try:
                if research and not topic.has_content:
                    found = research_topic_now(db, topic)
                    db.refresh(topic)
                    if found["sources"]:
                        summary["researched"] += 1
                        log.append(f"🔎 {topic.name}: {found['sources']} web source(s)")
                    else:
                        log.append(f"⚠️ {topic.name}: no web sources found")

                # One call per topic writes a mix of easy/medium/hard questions.
                missing = per_topic - sum(_question_counts(db, topic.id).values())
                if missing > 0:
                    report(index, topic.name)
                    result = generate_for_topic(
                        db, topic_id=topic.id, count=min(missing, 25), difficulty="mixed", allow_web_fallback=research
                    )
                    summary["generated"] += result["generated"]
                    mix = ", ".join(f"{sum(q['difficulty'] == lv for q in result['questions'])} {lv}" for lv in LEVELS)
                    log.append(f"✅ {topic.name}: +{result['generated']} ({mix}) via {result['source']}")
            except (NoContentError, GenerationError) as exc:
                summary["failed"] += 1
                log.append(f"❌ {topic.name}: {exc}"[:200])
                db.rollback()
            except Exception as exc:  # noqa: BLE001 - one bad topic must not stop the run
                summary["failed"] += 1
                logger.exception("Pipeline failed on topic %s", topic.id)
                log.append(f"❌ {topic.name}: {type(exc).__name__}: {exc}"[:200])
                db.rollback()

        return {"done": len(topics), "total": len(topics), "current": None, "log": log[-30:], **summary}
    finally:
        db.close()
