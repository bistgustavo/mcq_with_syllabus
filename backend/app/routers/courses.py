"""Courses and chapters: browse the syllabus tree, admin CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Chapter, Course, GeneratedQuestion, Topic, User
from app.schemas.chapter import ChapterCreate, ChapterRead, ChapterUpdate
from app.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseSummary,
    CourseTree,
    CourseUpdate,
    SyllabusImport,
    SyllabusImportResult,
)
from app.services.syllabus_service import export_syllabus, import_syllabus
from app.utils.cleanup import delete_chapters, delete_course, purge_topic_artifacts
from app.utils.security import get_current_user, require_admin

router = APIRouter(prefix="/api/v1", tags=["courses"])


def _get_course(db: Session, course_id: int, user: User) -> Course:
    course = db.get(Course, course_id)
    if course is None or (not course.is_published and not user.is_admin):
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found")
    return course


def _question_counts(db: Session, topic_ids: list[int]) -> dict[int, int]:
    if not topic_ids:
        return {}
    rows = db.execute(
        select(GeneratedQuestion.topic_id, func.count(GeneratedQuestion.id))
        .where(GeneratedQuestion.topic_id.in_(topic_ids))
        .group_by(GeneratedQuestion.topic_id)
    ).all()
    return {int(t): int(c) for t, c in rows}


# --------------------------------------------------------------------------- courses
@router.get("/courses", response_model=list[CourseSummary])
def list_courses(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[CourseSummary]:
    stmt = select(Course).order_by(Course.name)
    if not user.is_admin:
        stmt = stmt.where(Course.is_published.is_(True))
    courses = db.scalars(stmt).all()

    chapter_counts = dict(
        db.execute(select(Chapter.course_id, func.count(Chapter.id)).group_by(Chapter.course_id)).all()
    )
    topic_counts = dict(
        db.execute(
            select(Chapter.course_id, func.count(Topic.id)).join(Topic, Topic.chapter_id == Chapter.id).group_by(Chapter.course_id)
        ).all()
    )
    question_counts = dict(
        db.execute(
            select(Chapter.course_id, func.count(GeneratedQuestion.id))
            .join(Topic, Topic.chapter_id == Chapter.id)
            .join(GeneratedQuestion, GeneratedQuestion.topic_id == Topic.id)
            .group_by(Chapter.course_id)
        ).all()
    )
    return [
        CourseSummary(
            **CourseRead.model_validate(c).model_dump(),
            chapter_count=int(chapter_counts.get(c.id, 0)),
            topic_count=int(topic_counts.get(c.id, 0)),
            question_count=int(question_counts.get(c.id, 0)),
        )
        for c in courses
    ]


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Course:
    data = payload.model_dump()
    data["name"] = data["name"].strip()
    course = Course(**data)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/courses/{course_id}", response_model=CourseTree)
def get_course_tree(course_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """The full course → chapters (by order) → topics (by id) tree with question counts."""
    _get_course(db, course_id, user)
    course = db.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.chapters).selectinload(Chapter.topics))
    )
    topic_ids = [t.id for ch in course.chapters for t in ch.topics]
    counts = _question_counts(db, topic_ids)
    return {
        **CourseRead.model_validate(course).model_dump(),
        "chapters": [
            {
                **ChapterRead.model_validate(ch).model_dump(),
                "topics": [
                    {
                        "id": t.id,
                        "chapter_id": t.chapter_id,
                        "name": t.name,
                        "description": t.description,
                        "has_content": t.has_content,
                        "created_at": t.created_at,
                        "question_count": counts.get(t.id, 0),
                    }
                    for t in sorted(ch.topics, key=lambda t: t.id)
                ],
            }
            for ch in sorted(course.chapters, key=lambda c: (c.order, c.id))
        ],
    }


@router.patch("/courses/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int, payload: CourseUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)
) -> Course:
    course = _get_course(db, course_id, user)
    data = payload.model_dump(exclude_unset=True)
    nullable = {"description", "exam_name", "exam_instructions"}
    for key, value in data.items():
        if value is None and key not in nullable:
            continue
        setattr(course, key, value.strip() if key == "name" else value)
    db.commit()
    db.refresh(course)
    return course


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_course(course_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> Response:
    _get_course(db, course_id, user)
    topic_ids = delete_course(db, course_id)
    db.commit()
    purge_topic_artifacts(topic_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- chapters
@router.post("/chapters", response_model=ChapterRead, status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)) -> Chapter:
    _get_course(db, payload.course_id, user)
    order = payload.order
    if order is None:
        current_max = db.scalar(select(func.max(Chapter.order)).where(Chapter.course_id == payload.course_id))
        order = 0 if current_max is None else int(current_max) + 1
    chapter = Chapter(
        course_id=payload.course_id, name=payload.name.strip(), order=order, weight=payload.weight,
        paper=(payload.paper or "").strip() or None,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


def _get_chapter(db: Session, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_id} not found")
    return chapter


@router.get("/chapters/{chapter_id}", response_model=ChapterRead)
def get_chapter(chapter_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Chapter:
    chapter = _get_chapter(db, chapter_id)
    _get_course(db, chapter.course_id, user)
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(
    chapter_id: int, payload: ChapterUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> Chapter:
    chapter = _get_chapter(db, chapter_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        chapter.name = data["name"].strip()
    if data.get("order") is not None:
        chapter.order = data["order"]
    if data.get("weight") is not None:
        chapter.weight = data["weight"]
    if "paper" in data:
        chapter.paper = (data["paper"] or "").strip() or None
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chapter(chapter_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> Response:
    _get_chapter(db, chapter_id)
    topic_ids = delete_chapters(db, [chapter_id])
    db.commit()
    purge_topic_artifacts(topic_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- syllabus
@router.post("/courses/{course_id}/syllabus", response_model=SyllabusImportResult)
def import_course_syllabus(
    course_id: int, payload: SyllabusImport, db: Session = Depends(get_db), user: User = Depends(require_admin)
) -> dict:
    """Create/update chapters and topics from a pasted syllabus outline."""
    _get_course(db, course_id, user)
    result, removed_topic_ids = import_syllabus(db, course_id, payload.text, replace=payload.mode == "replace")
    db.commit()
    purge_topic_artifacts(removed_topic_ids)
    return result


@router.get("/courses/{course_id}/syllabus")
def get_course_syllabus(course_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """The course syllabus as editable plain text (same format the import accepts)."""
    _get_course(db, course_id, user)
    return {"text": export_syllabus(db, course_id)}
