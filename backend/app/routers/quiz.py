"""Quiz attempts (submit + history), dashboard, task status and admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Course, GeneratedQuestion, QuizAttempt, SyllabusDocument, Topic, User
from app.schemas.generated_question import validate_difficulty
from app.schemas.quiz_attempt import AdminOverview, AttemptSummary, QuizResult, QuizSubmission, UserDashboard
from app.schemas.user import AdminUserUpdate, UserRead
from app.services.attempt_service import (
    QuizValidationError,
    attempt_results,
    attempt_summaries,
    score_submission,
    user_dashboard,
)
from app.utils.security import get_current_user, require_admin
from app.utils.task_status import task_status_payload

router = APIRouter(prefix="/api/v1", tags=["quiz"])


def _result_payload(attempt: QuizAttempt, results: list[dict]) -> dict:
    return {
        "attempt_id": attempt.id,
        "topic_id": attempt.topic_id,
        "score": attempt.score,
        "total": attempt.total,
        "percent": round(100.0 * attempt.score / attempt.total, 1) if attempt.total else 0.0,
        "results": results,
        "difficulty": attempt.difficulty,
        "duration_seconds": attempt.duration_seconds,
        "created_at": attempt.created_at,
    }


@router.post("/quiz-attempts", response_model=QuizResult, status_code=201)
def submit_quiz(payload: QuizSubmission, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Score a quiz on the server and store the attempt."""
    if db.get(Topic, payload.topic_id) is None:
        raise HTTPException(status_code=404, detail=f"Topic {payload.topic_id} not found")
    difficulty = validate_difficulty(payload.difficulty) if payload.difficulty else None
    try:
        attempt, results = score_submission(
            db,
            user,
            payload.topic_id,
            [(a.question_id, a.selected_index) for a in payload.answers],
            difficulty=difficulty,
            duration_seconds=payload.duration_seconds,
        )
    except QuizValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _result_payload(attempt, results)


@router.get("/quiz-attempts/me", response_model=list[AttemptSummary])
def my_attempts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return attempt_summaries(db, user.id, limit=limit, offset=offset)


@router.get("/quiz-attempts/{attempt_id}", response_model=QuizResult)
def get_attempt(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    attempt = db.get(QuizAttempt, attempt_id)
    if attempt is None or (attempt.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Attempt not found")
    return _result_payload(attempt, attempt_results(db, attempt))


@router.get("/me/dashboard", response_model=UserDashboard)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return user_dashboard(db, user)


@router.get("/tasks/{task_id}")
def task_status(task_id: str, _: User = Depends(get_current_user)) -> dict:
    """State of a background task (ingestion or generation)."""
    return task_status_payload(task_id)


# --------------------------------------------------------------------------- admin
@router.get("/admin/overview", response_model=AdminOverview)
def admin_overview(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int(db.scalar(stmt) or 0)

    by_source = db.execute(
        select(GeneratedQuestion.source, func.count(GeneratedQuestion.id)).group_by(GeneratedQuestion.source)
    ).all()
    by_difficulty = db.execute(
        select(GeneratedQuestion.difficulty, func.count(GeneratedQuestion.id)).group_by(GeneratedQuestion.difficulty)
    ).all()
    return {
        "users": count(User),
        "courses": count(Course),
        "chapters": count(Chapter),
        "topics": count(Topic),
        "topics_with_content": count(Topic, Topic.has_content.is_(True)),
        "documents": count(SyllabusDocument, SyllabusDocument.source_type == "upload"),
        "questions": count(GeneratedQuestion),
        "attempts": count(QuizAttempt),
        "questions_by_source": {str(k): int(v) for k, v in by_source},
        "questions_by_difficulty": {str(k): int(v) for k, v in by_difficulty},
    }


@router.get("/admin/users", response_model=list[UserRead])
def admin_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)).all())


@router.patch("/admin/users/{user_id}", response_model=UserRead)
def admin_update_user(
    user_id: int, payload: AdminUserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and (payload.is_admin is False or payload.is_active is False):
        raise HTTPException(status_code=400, detail="You cannot demote or disable your own account")
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if payload.is_admin is not None:
        target.is_admin = payload.is_admin
    db.commit()
    db.refresh(target)
    return target
