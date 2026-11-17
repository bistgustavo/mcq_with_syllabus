"""Mock exams, course content pipeline (research + bank building) and branding."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSetting, Course, ExamAttempt, Topic, User
from app.services import exam_service
from app.utils.security import get_current_user, require_admin

router = APIRouter(prefix="/api/v1", tags=["exams"])


class ExamProgress(BaseModel):
    answers: list[int | None] = Field(default_factory=list, max_length=500)
    flagged: list[int] = Field(default_factory=list, max_length=500)


class StartExam(BaseModel):
    paper: str | None = Field(default=None, max_length=255)  # None = full exam (all papers)


class BuildBankRequest(BaseModel):
    per_topic: int = Field(default=15, ge=3, le=60)
    research: bool = True


class Branding(BaseModel):
    institution_name: str = Field(default="QuizForge", min_length=1, max_length=120)
    tagline: str = Field(default="Exam preparation, built from your syllabus", max_length=200)
    primary_color: str = Field(default="#1d4ed8", pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(default="#e11d48", pattern=r"^#[0-9a-fA-F]{6}$")
    logo_url: str | None = Field(default=None, max_length=500)
    support_email: str | None = Field(default=None, max_length=255)
    allow_signup: bool = True


def _course(db: Session, course_id: int, user: User) -> Course:
    course = db.get(Course, course_id)
    if course is None or (not course.is_published and not user.is_admin):
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _attempt(db: Session, attempt_id: int, user: User) -> ExamAttempt:
    attempt = db.get(ExamAttempt, attempt_id)
    if attempt is None or (attempt.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Exam not found")
    return attempt


# --------------------------------------------------------------------------- mock exams
@router.get("/courses/{course_id}/readiness")
def course_readiness(
    course_id: int, paper: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    try:
        return exam_service.readiness(db, _course(db, course_id, user), paper or None)
    except exam_service.ExamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/courses/{course_id}/mock-exams", status_code=201)
def start_mock_exam(
    course_id: int,
    payload: StartExam | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start a timed mock exam for one paper or the full exam (or resume the one already running)."""
    course = _course(db, course_id, user)
    try:
        paper = (payload.paper if payload else None) or None
        fresh = 0
        resuming = db.scalar(
            select(ExamAttempt.id).where(
                ExamAttempt.user_id == user.id, ExamAttempt.course_id == course.id, ExamAttempt.status == "in_progress",
                ExamAttempt.paper.is_(None) if paper is None else ExamAttempt.paper == paper,
            )
        )
        if not resuming:
            # The bank ran out of unseen questions for some chapters: let the AI write them now.
            from app.config import settings as _s

            short = exam_service.unseen_shortage(db, user, course, paper)
            if short and (_s.GROQ_API_KEY or _s.GEMINI_API_KEY):
                from app.database import SessionLocal

                db.rollback()
                fresh = exam_service.write_missing_questions(SessionLocal, short)
                db.expire_all()
        attempt = exam_service.start_exam(db, user, course, paper)
    except exam_service.ExamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Keep future papers fresh: top up topics where this student is running out of unseen questions.
    from app.workers.research_worker import queue_top_up

    queue_top_up(exam_service.low_stock_topics(db, user, course, paper))
    payload_out = exam_service.attempt_payload(db, attempt)
    payload_out["fresh_generated"] = fresh
    return payload_out


@router.get("/mock-exams/me")
def my_mock_exams(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(
        select(ExamAttempt, Course.name)
        .join(Course, Course.id == ExamAttempt.course_id)
        .where(ExamAttempt.user_id == user.id)
        .order_by(ExamAttempt.id.desc())
        .limit(100)
    ).all()
    return [exam_service.attempt_summary(a, name) for a, name in rows]


@router.get("/mock-exams/{attempt_id}")
def get_mock_exam(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    attempt = _attempt(db, attempt_id, user)
    if attempt.status == "in_progress" and exam_service.utcnow() > exam_service.ends_at(attempt):
        attempt = exam_service.submit_exam(db, attempt, attempt.answers or [], attempt.flagged or [])
    return exam_service.attempt_payload(db, attempt)


@router.put("/mock-exams/{attempt_id}/progress")
def save_mock_exam(
    attempt_id: int, payload: ExamProgress, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Autosave answers and flags (the exam survives a refresh or lost connection)."""
    attempt = _attempt(db, attempt_id, user)
    try:
        attempt = exam_service.save_progress(db, attempt, payload.answers, payload.flagged)
    except exam_service.ExamError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": attempt.status, "saved_at": exam_service.utcnow()}


@router.post("/mock-exams/{attempt_id}/submit")
def submit_mock_exam(
    attempt_id: int, payload: ExamProgress, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    attempt = _attempt(db, attempt_id, user)
    attempt = exam_service.submit_exam(db, attempt, payload.answers, payload.flagged)
    return exam_service.attempt_payload(db, attempt)


# --------------------------------------------------------------------------- content pipeline
def _queue(task, **kwargs) -> JSONResponse:
    try:
        result = task.delay(**kwargs)
    except Exception as exc:  # broker unreachable
        raise HTTPException(status_code=503, detail="Task queue unavailable — is the worker running?") from exc
    return JSONResponse(status_code=202, content={"task_id": result.id})


@router.post("/topics/{topic_id}/research", status_code=202)
def research_topic(topic_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Web-search this topic (guided by its syllabus text) and store the content."""
    from app.workers.research_worker import research_topic_task

    if db.get(Topic, topic_id) is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return _queue(research_topic_task, topic_id=topic_id)


@router.post("/courses/{course_id}/build-bank", status_code=202)
def build_bank(
    course_id: int, payload: BuildBankRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    """Research topics without notes and fill every topic's question bank (background job)."""
    from app.workers.research_worker import build_course_bank_task

    _course(db, course_id, user)
    current = _bank_job(db, course_id)
    if current and current["state"] in ("PENDING", "STARTED", "PROGRESS", "RETRY"):
        raise HTTPException(status_code=409, detail="A question-bank job is already running for this course")
    response = _queue(build_course_bank_task, course_id=course_id, per_topic=payload.per_topic, research=payload.research)
    import json

    task_id = json.loads(response.body)["task_id"]
    key = f"bank_job:{course_id}"
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value={"task_id": task_id}))
    else:
        row.value = {"task_id": task_id}
    db.commit()
    return response


def _job(db: Session, key: str) -> dict | None:
    from app.utils.task_status import task_status_payload

    row = db.get(AppSetting, key)
    if row is None or not row.value.get("task_id"):
        return None
    try:
        return task_status_payload(row.value["task_id"])
    except HTTPException:
        return None


def _remember_job(db: Session, key: str, task_id: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value={"task_id": task_id}))
    else:
        row.value = {"task_id": task_id}
    db.commit()


def _bank_job(db: Session, course_id: int) -> dict | None:
    from app.utils.task_status import task_status_payload

    row = db.get(AppSetting, f"bank_job:{course_id}")
    if row is None or not row.value.get("task_id"):
        return None
    try:
        return task_status_payload(row.value["task_id"])
    except HTTPException:
        return None


@router.get("/courses/{course_id}/build-bank")
def bank_job_status(course_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    """The latest question-bank job for this course (running or finished), if any."""
    _course(db, course_id, user)
    return {"job": _bank_job(db, course_id)}


# --------------------------------------------------------------------------- past papers & question sources
PAST_PAPER_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".txt"}


@router.post("/courses/{course_id}/past-papers", status_code=202)
def upload_past_paper(
    course_id: int,
    file: UploadFile = File(...),
    label: str = Form(..., min_length=2, max_length=200),
    paper: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Upload a past paper (PDF, scan or photo). It appears in the list and its MCQs are extracted."""
    from pathlib import Path

    from app.config import settings
    from app.models import PastPaper
    from app.workers.research_worker import process_past_paper_task

    _course(db, course_id, user)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in PAST_PAPER_SUFFIXES:
        raise HTTPException(status_code=400, detail="Upload a PDF, an image (PNG/JPG/TIFF) or a text file")
    folder = Path(settings.UPLOAD_DIR).resolve() / f"course-{course_id}" / "past-papers"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{uuid.uuid4().hex}{suffix}"
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB")
            out.write(chunk)
    row = PastPaper(course_id=course_id, title=label.strip(), source="upload", file_url=f"upload:{dest.name}",
                    stored_path=str(dest), status="found", year=None)
    db.add(row)
    db.commit()
    db.refresh(row)
    response = _queue(process_past_paper_task, paper_id=row.id)
    import json

    return JSONResponse(status_code=202, content={**json.loads(response.body), "paper_id": row.id})


def _paper_dict(p, admin: bool) -> dict:
    return {
        "id": p.id, "title": p.title, "source": p.source, "year": p.year, "status": p.status,
        "page_url": p.page_url, "file_url": None if p.file_url.startswith("upload:") else p.file_url,
        "has_file": bool(p.stored_path), "ocr": p.ocr, "pages": p.pages,
        "mcq_found": p.mcq_found, "mcq_added": p.mcq_added,
        "error": p.error if admin else None, "created_at": p.created_at,
    }


@router.get("/courses/{course_id}/past-papers")
def list_past_papers(course_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Papers for this course. Students see papers that have been read; admins see everything plus the job."""
    from app.models import PastPaper

    _course(db, course_id, user)
    stmt = select(PastPaper).where(PastPaper.course_id == course_id)
    if not user.is_admin:
        stmt = stmt.where(PastPaper.status.in_(["done", "no_mcq"]))
    papers = db.scalars(stmt.order_by(PastPaper.year.desc(), PastPaper.id.desc())).all()
    job = _job(db, f"paper_job:{course_id}") if user.is_admin else None
    return {"papers": [_paper_dict(p, user.is_admin) for p in papers], "job": job}


@router.post("/courses/{course_id}/past-papers/find", status_code=202)
def find_past_papers(course_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Search PSC, NRB and the web for past papers of this exam (background job)."""
    from app.workers.research_worker import find_past_papers_task

    _course(db, course_id, user)
    current = _job(db, f"paper_job:{course_id}")
    if current and current["state"] in ("PENDING", "STARTED", "PROGRESS", "RETRY"):
        raise HTTPException(status_code=409, detail="A paper search is already running for this course")
    response = _queue(find_past_papers_task, course_id=course_id)
    import json

    _remember_job(db, f"paper_job:{course_id}", json.loads(response.body)["task_id"])
    return response


@router.post("/past-papers/{paper_id}/process", status_code=202)
def reprocess_past_paper(paper_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.models import PastPaper
    from app.workers.research_worker import process_past_paper_task

    paper = db.get(PastPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper.status, paper.error = "found", None
    db.commit()
    return _queue(process_past_paper_task, paper_id=paper_id)


@router.get("/past-papers/{paper_id}/file")
def past_paper_file(paper_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The stored copy of a paper (uploads, or downloaded copies of online papers)."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.config import settings
    from app.models import PastPaper

    paper = db.get(PastPaper, paper_id)
    if paper is None or not paper.stored_path:
        raise HTTPException(status_code=404, detail="File not available")
    _course(db, paper.course_id, user)
    path = Path(paper.stored_path).resolve()
    if not path.is_file() or Path(settings.UPLOAD_DIR).resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="File not available")
    return FileResponse(path, filename=f"{paper.title[:80]}{path.suffix}")


@router.delete("/past-papers/{paper_id}", status_code=204)
def delete_past_paper(paper_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Remove a paper from the list (questions already extracted from it are kept)."""
    from fastapi import Response

    from app.models import PastPaper

    paper = db.get(PastPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    db.delete(paper)
    db.commit()
    return Response(status_code=204)


@router.post("/courses/{course_id}/collect-online", status_code=202)
def collect_online_questions(course_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Search the web for old questions of this exam and add the MCQs found (background job)."""
    from app.workers.research_worker import collect_online_questions_task

    _course(db, course_id, user)
    return _queue(collect_online_questions_task, course_id=course_id)


@router.get("/courses/{course_id}/question-sources")
def question_sources(course_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> dict:
    """How the course's question bank is made up: by source and by reference."""
    from sqlalchemy import func

    from app.models import Chapter, GeneratedQuestion

    _course(db, course_id, user)
    base = (
        select(GeneratedQuestion.source, GeneratedQuestion.reference, func.count(GeneratedQuestion.id))
        .join(Topic, Topic.id == GeneratedQuestion.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .where(Chapter.course_id == course_id)
        .group_by(GeneratedQuestion.source, GeneratedQuestion.reference)
    )
    rows = db.execute(base).all()
    by_kind: dict[str, int] = {}
    refs = []
    for source, reference, n in rows:
        kind = source if source in ("notes", "past_paper", "online") else "ai"
        by_kind[kind] = by_kind.get(kind, 0) + int(n)
        if kind in ("past_paper", "online") and reference:
            refs.append({"kind": kind, "reference": reference, "count": int(n)})
    refs.sort(key=lambda r: -r["count"])
    return {"by_kind": by_kind, "references": refs[:100], "total": sum(by_kind.values())}


# --------------------------------------------------------------------------- branding
BRANDING_KEY = "branding"


def get_branding(db: Session) -> Branding:
    row = db.get(AppSetting, BRANDING_KEY)
    return Branding(**(row.value if row else {}))


@router.get("/settings/branding", response_model=Branding)
def read_branding(db: Session = Depends(get_db)) -> Branding:
    """Public: the institution's name, colours and logo (used by the login/landing pages)."""
    return get_branding(db)


@router.put("/settings/branding", response_model=Branding)
def update_branding(payload: Branding, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Branding:
    row = db.get(AppSetting, BRANDING_KEY)
    if row is None:
        db.add(AppSetting(key=BRANDING_KEY, value=payload.model_dump()))
    else:
        row.value = payload.model_dump()
    db.commit()
    return payload


@router.get("/settings/public-stats")
def public_stats(db: Session = Depends(get_db)) -> dict:
    """Public counters for the landing page."""
    from sqlalchemy import func

    from app.models import GeneratedQuestion

    courses = db.scalars(select(Course).where(Course.is_published.is_(True)).order_by(Course.name)).all()
    return {
        "questions": int(db.scalar(select(func.count(GeneratedQuestion.id))) or 0),
        "courses": [
            {"id": c.id, "name": c.name, "exam_name": c.exam_name, "description": c.description,
             "exam_question_count": c.exam_question_count, "exam_duration_minutes": c.exam_duration_minutes,
             "negative_marking": c.negative_marking}
            for c in courses
        ],
    }
