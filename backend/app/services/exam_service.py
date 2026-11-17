"""Mock exams: paper assembly by chapter weight, timed attempts, negative marking."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chapter, Course, ExamAttempt, GeneratedQuestion, QuizAttempt, Topic, User
from app.models.exam_attempt import EXAM_IN_PROGRESS, EXAM_SUBMITTED

GRACE_SECONDS = 30  # network latency allowance after the clock hits zero


class ExamError(ValueError):
    """Raised when an exam cannot be started or submitted."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """MySQL returns naive datetimes; they are stored in UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def chapter_quotas(chapters: list[Chapter], total: int) -> dict[int, int]:
    """Questions per chapter: explicit weights first, the rest split evenly."""
    quotas = {c.id: max(0, c.weight or 0) for c in chapters}
    unweighted = [c for c in chapters if not c.weight]
    remaining = max(0, total - sum(quotas.values()))
    if unweighted and remaining:
        base, extra = divmod(remaining, len(unweighted))
        for i, c in enumerate(unweighted):
            quotas[c.id] = base + (1 if i < extra else 0)
    return quotas


def course_papers(db: Session, course_id: int) -> list[str]:
    """Distinct paper labels of a course, in syllabus order ([] for single-paper courses)."""
    seen: list[str] = []
    for paper in db.scalars(
        select(Chapter.paper).where(Chapter.course_id == course_id).order_by(Chapter.order, Chapter.id)
    ).all():
        if paper and paper not in seen:
            seen.append(paper)
    return seen


def _selected_chapters(db: Session, course: Course, paper: str | None) -> list[Chapter]:
    stmt = select(Chapter).where(Chapter.course_id == course.id).order_by(Chapter.order, Chapter.id)
    if paper:
        stmt = stmt.where(Chapter.paper == paper)
    return list(db.scalars(stmt).all())


def paper_plan(db: Session, course: Course, paper: str | None) -> tuple[list[Chapter], dict[int, int], int, int]:
    """(chapters, quotas, question_count, duration_minutes) for one paper or the full exam.

    ``exam_question_count`` / ``exam_duration_minutes`` are per paper; the full
    exam of a multi-paper course is all papers back to back.
    """
    papers = course_papers(db, course.id)
    if paper and paper not in papers:
        raise ExamError(f"Unknown paper: {paper}")
    chapters = _selected_chapters(db, course, paper)
    if paper or not papers:
        quotas = chapter_quotas(chapters, course.exam_question_count)
        return chapters, quotas, sum(quotas.values()), course.exam_duration_minutes
    quotas: dict[int, int] = {}
    for p in papers:
        quotas.update(chapter_quotas([c for c in chapters if c.paper == p], course.exam_question_count))
    unpapered = [c for c in chapters if not c.paper]
    if unpapered:
        quotas.update(chapter_quotas(unpapered, 0))
    return chapters, quotas, sum(quotas.values()), course.exam_duration_minutes * len(papers)


def readiness(db: Session, course: Course, paper: str | None = None) -> dict:
    """How many questions each chapter needs for one paper vs. has in the bank."""
    chapters, quotas, _, _ = paper_plan(db, course, paper)
    rows = []
    counts = dict(
        db.execute(
            select(Topic.chapter_id, func.count(GeneratedQuestion.id))
            .join(GeneratedQuestion, GeneratedQuestion.topic_id == Topic.id)
            .where(Topic.chapter_id.in_([c.id for c in chapters] or [0]))
            .group_by(Topic.chapter_id)
        ).all()
    )
    for c in chapters:
        count = int(counts.get(c.id, 0))
        rows.append({"chapter_id": c.id, "chapter_name": c.name, "needed": quotas.get(c.id, 0), "available": count})
    paper_size = sum(r["needed"] for r in rows)
    ready = sum(min(r["needed"], r["available"]) for r in rows)
    return {
        "course_id": course.id,
        "paper": paper,
        "papers": course_papers(db, course.id),
        "marking": marking_scheme(course, course_papers(db, course.id)),
        "paper_size": paper_size,
        "ready_questions": ready,
        "is_ready": paper_size > 0 and ready >= paper_size,
        "chapters": rows,
    }


def low_stock_topics(db: Session, user: User, course: Course, paper: str | None, minimum: int = 3) -> list[int]:
    """Topics of the paper where this user has fewer than ``minimum`` unseen questions left."""
    from app.services.attempt_service import last_seen

    seen = last_seen(db, user)
    chapters, _, _, _ = paper_plan(db, course, paper)
    rows = db.execute(
        select(Topic.id, GeneratedQuestion.id)
        .outerjoin(GeneratedQuestion, GeneratedQuestion.topic_id == Topic.id)
        .where(Topic.chapter_id.in_([c.id for c in chapters] or [0]))
    ).all()
    unseen: dict[int, int] = defaultdict(int)
    for topic_id, qid in rows:
        unseen[topic_id] += int(qid is not None and qid not in seen)
    return [tid for tid, n in unseen.items() if n < minimum]


def build_sections(db: Session, user: User, course: Course, paper: str | None = None) -> list[tuple[str | None, list[int]]]:
    """Question ids per paper section, each following its own chapter weights.

    Unseen questions come first, then the least recently seen. A short chapter is
    topped up from spare questions of the SAME paper, so sections never mix.
    """
    from app.services.attempt_service import last_seen

    chapters, quotas, _, _ = paper_plan(db, course, paper)
    seen = last_seen(db, user)

    groups: dict[str | None, list[Chapter]] = {}
    for c in chapters:
        groups.setdefault(c.paper, []).append(c)

    sections: list[tuple[str | None, list[int]]] = []
    for label, group in groups.items():
        pools: dict[int, list[int]] = {}
        for c in group:
            ids = list(
                db.scalars(
                    select(GeneratedQuestion.id).join(Topic, Topic.id == GeneratedQuestion.topic_id).where(Topic.chapter_id == c.id)
                ).all()
            )
            unseen = [i for i in ids if i not in seen]
            random.shuffle(unseen)
            old = sorted((i for i in ids if i in seen), key=lambda i: seen[i])  # least recently seen first
            pools[c.id] = unseen + old
        picked: list[int] = []
        shortfall = 0
        for c in group:
            take = pools[c.id][: quotas.get(c.id, 0)]
            pools[c.id] = pools[c.id][len(take):]
            shortfall += quotas.get(c.id, 0) - len(take)
            picked.extend(take)
        if shortfall:
            spare = [i for c in group for i in pools[c.id]]
            random.shuffle(spare)
            picked.extend(spare[:shortfall])
        if picked:
            sections.append((label, picked))
    return sections


def build_paper(db: Session, user: User, course: Course, paper: str | None = None) -> list[int]:
    """Question ids for a paper (all sections in syllabus order)."""
    return [i for _, ids in build_sections(db, user, course, paper) for i in ids]


def marking_scheme(course: Course, papers: list[str] | None = None) -> dict:
    """The marking rules for this course's mock tests, from its exam pattern (the syllabus)."""
    m = course.marks_per_question or 1.0
    neg = course.negative_marking or 0.0
    deduction = round(m * neg, 3)
    multi = bool(papers and len(papers) > 1)
    if course.pass_rule == "overall" or not multi:
        pass_text = f"Pass mark: {course.pass_percent}% of the total marks."
    else:
        pass_text = f"Pass mark: {course.pass_percent}% in EACH paper separately; failing any paper fails the exam."
    lines = [
        f"Each correct answer: +{m:g} mark{'s' if m != 1 else ''}.",
        f"Each wrong answer: −{deduction:g} mark ({round(neg * 100):g}% of the question's mark)." if neg else "No negative marking.",
        "Unanswered questions: 0 (no deduction).",
        pass_text,
    ]
    return {"marks_per_question": m, "negative_marking": neg, "deduction_per_wrong": deduction,
            "pass_percent": course.pass_percent, "pass_rule": course.pass_rule, "lines": lines}


def _public_questions(db: Session, ids: list[int]) -> list[dict]:
    rows = db.execute(
        select(GeneratedQuestion, Topic.name, Chapter.name)
        .join(Topic, Topic.id == GeneratedQuestion.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .where(GeneratedQuestion.id.in_(ids))
    ).all()
    by_id = {q.id: (q, t, c) for q, t, c in rows}
    out = []
    for qid in ids:
        if qid not in by_id:
            continue
        q, topic_name, chapter_name = by_id[qid]
        out.append(
            {
                "id": q.id,
                "question_text": q.question_text,
                "options": list(q.options or []),
                "difficulty": q.difficulty,
                "topic_name": topic_name,
                "chapter_name": chapter_name,
            }
        )
    return out


def ends_at(attempt: ExamAttempt) -> datetime:
    return _aware(attempt.started_at) + timedelta(seconds=attempt.time_limit_seconds)


def start_exam(db: Session, user: User, course: Course, paper: str | None = None) -> ExamAttempt:
    """Resume the user's running exam for this course and paper, or start a new one."""
    running = db.scalar(
        select(ExamAttempt).where(
            ExamAttempt.user_id == user.id,
            ExamAttempt.course_id == course.id,
            ExamAttempt.status == EXAM_IN_PROGRESS,
            ExamAttempt.paper.is_(None) if paper is None else ExamAttempt.paper == paper,
        )
    )
    if running is not None:
        if utcnow() <= ends_at(running) + timedelta(seconds=GRACE_SECONDS):
            return running
        submit_exam(db, running, running.answers or [], running.flagged or [])  # time ran out while away

    _, _, _, minutes = paper_plan(db, course, paper)
    built = build_sections(db, user, course, paper)
    ids = [i for _, section_ids in built for i in section_ids]
    sections, start = [], 0
    for label, section_ids in built:
        sections.append({"paper": label, "start": start, "count": len(section_ids),
                         "minutes": course.exam_duration_minutes if (len(built) > 1 or label) else minutes})
        start += len(section_ids)
    if not ids:
        raise ExamError("This course has no questions yet. Ask your administrator to build the question bank.")
    attempt = ExamAttempt(
        user_id=user.id,
        course_id=course.id,
        status=EXAM_IN_PROGRESS,
        paper=paper,
        question_ids=ids,
        answers=[None] * len(ids),
        flagged=[],
        time_limit_seconds=minutes * 60,
        negative_marking=course.negative_marking,
        pass_percent=course.pass_percent,
        marks_per_question=course.marks_per_question or 1.0,
        pass_rule=course.pass_rule or "per_paper",
        sections=sections,
        started_at=utcnow(),
        total=len(ids),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _normalise_answers(attempt: ExamAttempt, answers: list[int | None]) -> list[int | None]:
    n = len(attempt.question_ids)
    out: list[int | None] = []
    for i in range(n):
        value = answers[i] if i < len(answers) else None
        out.append(value if isinstance(value, int) and 0 <= value <= 3 else None)
    return out


def save_progress(db: Session, attempt: ExamAttempt, answers: list[int | None], flagged: list[int]) -> ExamAttempt:
    if attempt.status != EXAM_IN_PROGRESS:
        raise ExamError("This exam has already been submitted")
    if utcnow() > ends_at(attempt) + timedelta(seconds=GRACE_SECONDS):
        return submit_exam(db, attempt, attempt.answers or [], attempt.flagged or [])
    attempt.answers = _normalise_answers(attempt, answers)
    attempt.flagged = sorted({int(f) for f in flagged if 0 <= int(f) < len(attempt.question_ids)})
    db.commit()
    db.refresh(attempt)
    return attempt


def submit_exam(db: Session, attempt: ExamAttempt, answers: list[int | None], flagged: list[int]) -> ExamAttempt:
    """Score the attempt. Answers sent after the time limit (+grace) are ignored."""
    if attempt.status == EXAM_SUBMITTED:
        return attempt
    late = utcnow() > ends_at(attempt) + timedelta(seconds=GRACE_SECONDS)
    final = _normalise_answers(attempt, attempt.answers or [] if late else answers)

    rows = db.execute(
        select(GeneratedQuestion.id, GeneratedQuestion.correct_index, Chapter.id, Chapter.name)
        .join(Topic, Topic.id == GeneratedQuestion.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .where(GeneratedQuestion.id.in_(attempt.question_ids))
    ).all()
    key = {qid: (correct, cid, cname) for qid, correct, cid, cname in rows}

    correct = wrong = skipped = 0
    chapters: dict[int, dict] = defaultdict(lambda: {"correct": 0, "wrong": 0, "skipped": 0, "total": 0})
    for qid, chosen in zip(attempt.question_ids, final):
        if qid not in key:  # question deleted mid-exam: not counted
            continue
        right, cid, cname = key[qid]
        bucket = chapters[cid]
        bucket["chapter_id"], bucket["chapter_name"] = cid, cname
        bucket["total"] += 1
        if chosen is None:
            skipped += 1
            bucket["skipped"] += 1
        elif chosen == right:
            correct += 1
            bucket["correct"] += 1
        else:
            wrong += 1
            bucket["wrong"] += 1

    neg = attempt.negative_marking or 0.0
    m = attempt.marks_per_question or 1.0
    total = correct + wrong + skipped
    breakdown = []
    for b in chapters.values():
        b_score = m * b["correct"] - neg * m * b["wrong"]
        b["score"] = round(b_score, 2)
        b["percent"] = round(100 * b_score / (m * b["total"]), 1) if b["total"] else 0.0
        breakdown.append(b)
    breakdown.sort(key=lambda b: b["percent"])

    # Per paper section (the whole exam is one section for single-paper courses).
    section_results = []
    for sec in attempt.sections or [{"paper": attempt.paper, "start": 0, "count": len(attempt.question_ids)}]:
        c = w = sk = 0
        for qid, chosen in list(zip(attempt.question_ids, final))[sec["start"] : sec["start"] + sec["count"]]:
            if qid not in key:
                continue
            if chosen is None:
                sk += 1
            elif chosen == key[qid][0]:
                c += 1
            else:
                w += 1
        n = c + w + sk
        sc = round(m * c - neg * m * w, 2)
        pct = round(100 * sc / (m * n), 1) if n else 0.0
        section_results.append({"paper": sec.get("paper"), "correct": c, "wrong": w, "skipped": sk, "total": n,
                                "score": sc, "max_score": round(m * n, 2), "percent": pct,
                                "passed": pct >= attempt.pass_percent})
    attempt.section_results = section_results

    attempt.answers = final
    attempt.flagged = sorted({int(f) for f in flagged if 0 <= int(f) < len(attempt.question_ids)}) if not late else attempt.flagged
    attempt.correct, attempt.wrong, attempt.skipped, attempt.total = correct, wrong, skipped, total
    attempt.score = round(m * correct - neg * m * wrong, 2)
    attempt.chapter_breakdown = breakdown
    attempt.status = EXAM_SUBMITTED
    attempt.submitted_at = utcnow()
    db.commit()
    db.refresh(attempt)
    return attempt


def percent(attempt: ExamAttempt) -> float:
    max_score = (attempt.marks_per_question or 1.0) * attempt.total
    return round(100 * attempt.score / max_score, 1) if attempt.total else 0.0


def exam_passed(attempt: ExamAttempt) -> bool:
    """Apply the course's pass rule: every paper must pass, or the combined score must."""
    if attempt.status != EXAM_SUBMITTED:
        return False
    results = attempt.section_results or []
    if attempt.pass_rule == "per_paper" and len(results) > 1:
        return all(r["passed"] for r in results)
    return percent(attempt) >= attempt.pass_percent


def attempt_payload(db: Session, attempt: ExamAttempt) -> dict:
    """Public view: questions without answers while running, full review once submitted."""
    course = db.get(Course, attempt.course_id)
    base = {
        "id": attempt.id,
        "course_id": attempt.course_id,
        "course_name": course.name if course else "",
        "exam_name": (course.exam_name or course.name) if course else "",
        "instructions": course.exam_instructions if course else None,
        "status": attempt.status,
        "paper": attempt.paper,
        "started_at": _aware(attempt.started_at),
        "ends_at": ends_at(attempt),
        "server_now": utcnow(),
        "time_limit_seconds": attempt.time_limit_seconds,
        "negative_marking": attempt.negative_marking,
        "pass_percent": attempt.pass_percent,
        "marks_per_question": attempt.marks_per_question or 1.0,
        "pass_rule": attempt.pass_rule,
        "marking": marking_scheme(course, [s["paper"] for s in (attempt.sections or []) if s.get("paper")]) if course else None,
        "sections": attempt.sections or [{"paper": attempt.paper, "start": 0, "count": len(attempt.question_ids),
                                          "minutes": attempt.time_limit_seconds // 60}],
        "answers": attempt.answers or [None] * len(attempt.question_ids),
        "flagged": attempt.flagged or [],
        "questions": _public_questions(db, list(attempt.question_ids)),
    }
    if attempt.status != EXAM_SUBMITTED:
        return base

    review = {
        q.id: q for q in db.scalars(select(GeneratedQuestion).where(GeneratedQuestion.id.in_(attempt.question_ids))).all()
    }
    for q in base["questions"]:
        full = review.get(q["id"])
        q["correct_index"] = full.correct_index if full else None
        q["explanation"] = full.explanation if full else None
        q["source"] = full.source if full else None
        q["reference"] = full.reference if full else None
    pct = percent(attempt)
    duration = (
        int((_aware(attempt.submitted_at) - _aware(attempt.started_at)).total_seconds()) if attempt.submitted_at else None
    )
    base.update(
        {
            "submitted_at": _aware(attempt.submitted_at) if attempt.submitted_at else None,
            "duration_seconds": min(duration, attempt.time_limit_seconds) if duration is not None else None,
            "correct": attempt.correct,
            "wrong": attempt.wrong,
            "skipped": attempt.skipped,
            "total": attempt.total,
            "score": attempt.score,
            "max_score": round((attempt.marks_per_question or 1.0) * attempt.total, 2),
            "percent": pct,
            "passed": exam_passed(attempt),
            "section_results": attempt.section_results or [],
            "chapter_breakdown": attempt.chapter_breakdown or [],
        }
    )
    return base


def attempt_summary(attempt: ExamAttempt, course_name: str) -> dict:
    return {
        "id": attempt.id,
        "course_id": attempt.course_id,
        "course_name": course_name,
        "paper": attempt.paper,
        "status": attempt.status,
        "started_at": _aware(attempt.started_at),
        "submitted_at": _aware(attempt.submitted_at) if attempt.submitted_at else None,
        "score": attempt.score,
        "total": attempt.total,
        "percent": percent(attempt),
        "passed": exam_passed(attempt),
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "skipped": attempt.skipped,
    }


# --------------------------------------------------------------------------- on-demand questions
def unseen_shortage(db: Session, user: User, course: Course, paper: str | None) -> dict[int, int]:
    """chapter_id -> how many more unseen questions this student needs for one paper."""
    from app.services.attempt_service import last_seen

    seen = last_seen(db, user)
    chapters, quotas, _, _ = paper_plan(db, course, paper)
    short: dict[int, int] = {}
    for c in chapters:
        ids = db.scalars(
            select(GeneratedQuestion.id).join(Topic, Topic.id == GeneratedQuestion.topic_id).where(Topic.chapter_id == c.id)
        ).all()
        unseen = sum(1 for i in ids if i not in seen)
        if quotas.get(c.id, 0) > unseen:
            short[c.id] = quotas[c.id] - unseen
    return short


def write_missing_questions(db_factory, short: dict[int, int], budget_seconds: float = 45.0) -> int:
    """Write fresh questions for chapters that ran out, from the syllabus and notes.

    Cloud models first (fast); when they are rate-limited the local model takes
    over. The student waits at most ``budget_seconds``: work still running after
    that keeps going in the background and its questions are saved for the next
    paper. Returns how many questions were ready in time.
    """
    import concurrent.futures as cf

    from app.services.quiz_service import generate_for_topic

    def one_chapter(chapter_id: int, missing: int) -> int:
        db = db_factory()
        try:
            counts = dict(
                db.execute(
                    select(Topic.id, func.count(GeneratedQuestion.id))
                    .outerjoin(GeneratedQuestion, GeneratedQuestion.topic_id == Topic.id)
                    .where(Topic.chapter_id == chapter_id)
                    .group_by(Topic.id)
                ).all()
            )
            db.rollback()
            topics = sorted(counts, key=lambda t: counts[t])  # least-covered topics first
            written = 0
            for topic_id in topics[: max(1, (missing + 4) // 5)]:
                if written >= missing:
                    break
                try:
                    r = generate_for_topic(db, topic_id=topic_id, count=min(10, max(3, missing - written)),
                                           difficulty="mixed")
                    written += r["generated"]
                except Exception as exc:  # noqa: BLE001 - fall back to repeats + background top-up
                    db.rollback()
                    import logging

                    logging.getLogger(__name__).info("On-demand generation for chapter %s stopped: %s", chapter_id, exc)
                    break
            return written
        finally:
            db.close()

    total = 0
    pool = cf.ThreadPoolExecutor(max_workers=3, thread_name_prefix="exam-topup")
    futures = [pool.submit(one_chapter, cid, n) for cid, n in short.items()]
    done, _ = cf.wait(futures, timeout=budget_seconds)
    # Do not block on stragglers (e.g. the local model): they finish in the background.
    pool.shutdown(wait=False)
    for f in done:
        try:
            total += f.result()
        except Exception:  # noqa: BLE001
            pass
    return total
