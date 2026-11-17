"""Quiz assembly, server-side scoring and progress statistics."""

from __future__ import annotations

import random
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chapter, Course, ExamAttempt, GeneratedQuestion, QuizAttempt, Topic, User


class QuizValidationError(ValueError):
    """Submitted answers do not match the topic's questions."""


def _percent(score: int, total: int) -> float:
    return round(100.0 * score / total, 1) if total else 0.0


def last_seen(db: Session, user: User) -> dict[int, float]:
    """question id -> when this user last saw it (epoch seconds), across practice and mock tests."""
    out: dict[int, float] = {}
    rows = list(db.execute(select(QuizAttempt.question_ids, QuizAttempt.created_at).where(QuizAttempt.user_id == user.id)).all())
    rows += list(db.execute(select(ExamAttempt.question_ids, ExamAttempt.started_at).where(ExamAttempt.user_id == user.id)).all())
    for ids, when in rows:
        ts = when.timestamp() if when else 0.0
        for qid in ids or []:
            out[int(qid)] = max(out.get(int(qid), 0.0), ts)
    return out


def order_fresh_first(pool: list, seen: dict[int, float]) -> list:
    """Unseen questions (shuffled) first, then seen ones from least to most recently seen."""
    unseen = [q for q in pool if q.id not in seen]
    random.shuffle(unseen)
    old = sorted((q for q in pool if q.id in seen), key=lambda q: seen[q.id])
    return unseen + old


def pick_questions(
    db: Session, user: User, topic_id: int, count: int, difficulty: str | None = None
) -> list[GeneratedQuestion]:
    """Choose ``count`` questions: never-seen first, then the least recently seen."""
    stmt = select(GeneratedQuestion).where(GeneratedQuestion.topic_id == topic_id)
    if difficulty:
        stmt = stmt.where(GeneratedQuestion.difficulty == difficulty)
    pool = list(db.scalars(stmt).all())
    return order_fresh_first(pool, last_seen(db, user))[:count]


def unseen_count(db: Session, user: User, topic_id: int, difficulty: str | None = None) -> int:
    stmt = select(GeneratedQuestion.id).where(GeneratedQuestion.topic_id == topic_id)
    if difficulty:
        stmt = stmt.where(GeneratedQuestion.difficulty == difficulty)
    seen = last_seen(db, user)
    return sum(1 for qid in db.scalars(stmt).all() if qid not in seen)


def score_submission(
    db: Session,
    user: User,
    topic_id: int,
    answers: list[tuple[int, int | None]],
    difficulty: str | None = None,
    duration_seconds: int | None = None,
) -> tuple[QuizAttempt, list[dict]]:
    """Score ``answers`` (question_id, selected_index) and store the attempt."""
    ordered_ids: list[int] = []
    chosen: dict[int, int | None] = {}
    for question_id, selected in answers:
        if question_id in chosen:
            raise QuizValidationError(f"Question {question_id} was answered more than once")
        ordered_ids.append(question_id)
        chosen[question_id] = selected

    questions = {
        q.id: q
        for q in db.scalars(select(GeneratedQuestion).where(GeneratedQuestion.id.in_(ordered_ids))).all()
    }
    unknown = [qid for qid in ordered_ids if qid not in questions or questions[qid].topic_id != topic_id]
    if unknown:
        raise QuizValidationError(f"Questions {unknown} do not belong to topic {topic_id}")

    results: list[dict] = []
    score = 0
    for qid in ordered_ids:
        q = questions[qid]
        selected = chosen[qid]
        correct = selected is not None and selected == q.correct_index
        score += int(correct)
        results.append(
            {
                "question_id": q.id,
                "question_text": q.question_text,
                "options": list(q.options or []),
                "selected_index": selected,
                "correct_index": q.correct_index,
                "is_correct": correct,
                "explanation": q.explanation,
                "source": q.source,
                "reference": q.reference,
            }
        )

    attempt = QuizAttempt(
        user_id=user.id,
        topic_id=topic_id,
        question_ids=ordered_ids,
        answers=[chosen[q] for q in ordered_ids],
        score=score,
        total=len(ordered_ids),
        difficulty=difficulty,
        duration_seconds=duration_seconds,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt, results


def attempt_results(db: Session, attempt: QuizAttempt) -> list[dict]:
    """Rebuild the per-question review of a stored attempt."""
    ids = [int(i) for i in (attempt.question_ids or [])]
    answers = list(attempt.answers or [None] * len(ids))
    questions = {q.id: q for q in db.scalars(select(GeneratedQuestion).where(GeneratedQuestion.id.in_(ids))).all()}
    results = []
    for qid, selected in zip(ids, answers):
        q = questions.get(qid)
        if q is None:  # question deleted since
            continue
        results.append(
            {
                "question_id": q.id,
                "question_text": q.question_text,
                "options": list(q.options or []),
                "selected_index": selected,
                "correct_index": q.correct_index,
                "is_correct": selected is not None and selected == q.correct_index,
                "explanation": q.explanation,
                "source": q.source,
                "reference": q.reference,
            }
        )
    return results


def attempt_summaries(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = db.execute(
        select(QuizAttempt, Topic.name, Course.name)
        .join(Topic, Topic.id == QuizAttempt.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .where(QuizAttempt.user_id == user_id)
        .order_by(QuizAttempt.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": a.id,
            "topic_id": a.topic_id,
            "topic_name": topic_name,
            "course_name": course_name,
            "score": a.score,
            "total": a.total,
            "percent": _percent(a.score, a.total),
            "difficulty": a.difficulty,
            "duration_seconds": a.duration_seconds,
            "created_at": a.created_at,
        }
        for a, topic_name, course_name in rows
    ]


def user_dashboard(db: Session, user: User) -> dict:
    rows = db.execute(
        select(QuizAttempt, Topic.name, Course.name)
        .join(Topic, Topic.id == QuizAttempt.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .where(QuizAttempt.user_id == user.id)
        .order_by(QuizAttempt.id.asc())
    ).all()

    per_topic: dict[int, dict] = defaultdict(lambda: {"percents": [], "last": None})
    answered = correct = 0
    percents: list[float] = []
    for attempt, topic_name, course_name in rows:
        pct = _percent(attempt.score, attempt.total)
        percents.append(pct)
        answered += attempt.total
        correct += attempt.score
        entry = per_topic[attempt.topic_id]
        entry["topic_name"] = topic_name
        entry["course_name"] = course_name
        entry["percents"].append(pct)
        entry["last"] = attempt.created_at

    topics = [
        {
            "topic_id": tid,
            "topic_name": e["topic_name"],
            "course_name": e["course_name"],
            "attempts": len(e["percents"]),
            "avg_percent": round(sum(e["percents"]) / len(e["percents"]), 1),
            "best_percent": max(e["percents"]),
            "last_attempt_at": e["last"],
        }
        for tid, e in per_topic.items()
    ]
    topics.sort(key=lambda t: t["last_attempt_at"] or 0, reverse=True)
    weakest = sorted(topics, key=lambda t: t["avg_percent"])[:5]

    return {
        "attempts": len(rows),
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else 0.0,
        "best_percent": max(percents) if percents else 0.0,
        "questions_answered": answered,
        "correct_answers": correct,
        "topics_practiced": len(topics),
        "recent": attempt_summaries(db, user.id, limit=10),
        "topics": topics,
        "weakest_topics": weakest,
    }


def topic_stats(db: Session, topic_id: int) -> dict:
    question_count = db.scalar(select(func.count(GeneratedQuestion.id)).where(GeneratedQuestion.topic_id == topic_id)) or 0
    by_source = dict(
        db.execute(
            select(GeneratedQuestion.source, func.count(GeneratedQuestion.id))
            .where(GeneratedQuestion.topic_id == topic_id)
            .group_by(GeneratedQuestion.source)
        ).all()
    )
    attempts = db.execute(select(QuizAttempt.score, QuizAttempt.total).where(QuizAttempt.topic_id == topic_id)).all()
    percents = [_percent(s, t) for s, t in attempts]
    return {
        "topic_id": topic_id,
        "question_count": int(question_count),
        "attempts": len(percents),
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else 0.0,
        "best_percent": max(percents) if percents else 0.0,
        "by_source": {str(k): int(v) for k, v in by_source.items()},
    }
