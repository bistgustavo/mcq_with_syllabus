"""Course schemas: CRUD payloads and the full course -> chapters -> topics tree."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chapter import ChapterTree


class CourseCreate(BaseModel):
    """Payload for creating a course."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_published: bool = True
    exam_name: str | None = Field(default=None, max_length=255)
    exam_question_count: int = Field(default=50, ge=5, le=200)
    exam_duration_minutes: int = Field(default=45, ge=5, le=300)
    negative_marking: float = Field(default=0.2, ge=0, le=1)
    pass_percent: int = Field(default=40, ge=0, le=100)
    exam_instructions: str | None = None
    marks_per_question: float = Field(default=1.0, gt=0, le=10)
    pass_rule: str = Field(default="per_paper", pattern="^(per_paper|overall)$")


class CourseUpdate(BaseModel):
    """Partial update of a course."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_published: bool | None = None
    exam_name: str | None = Field(default=None, max_length=255)
    exam_question_count: int | None = Field(default=None, ge=5, le=200)
    exam_duration_minutes: int | None = Field(default=None, ge=5, le=300)
    negative_marking: float | None = Field(default=None, ge=0, le=1)
    pass_percent: int | None = Field(default=None, ge=0, le=100)
    exam_instructions: str | None = None
    marks_per_question: float | None = Field(default=None, gt=0, le=10)
    pass_rule: str | None = Field(default=None, pattern="^(per_paper|overall)$")


class CourseRead(BaseModel):
    """Public representation of a course."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_published: bool = True
    exam_name: str | None = None
    exam_question_count: int = 50
    exam_duration_minutes: int = 45
    negative_marking: float = 0.2
    pass_percent: int = 40
    exam_instructions: str | None = None
    marks_per_question: float = 1.0
    pass_rule: str = "per_paper"
    created_at: datetime | None = None


class CourseSummary(CourseRead):
    """Course card for listings, with aggregate counts."""

    chapter_count: int = 0
    topic_count: int = 0
    question_count: int = 0


class CourseTree(CourseRead):
    """Course with its chapters (ordered by ``order``) and their topics."""

    chapters: list[ChapterTree] = Field(default_factory=list)


class SyllabusImport(BaseModel):
    """Plain-text syllabus outline.

    Format: one chapter per line (optionally numbered, or starting with '#'),
    topics on following lines starting with '-', '*' or '•'. A topic line may
    carry its syllabus detail after ':' (e.g. "- OSI model: layers, functions").
    A chapter line may end with "[10]" to set its weight (questions in the mock paper).
    """

    text: str = Field(..., min_length=3, max_length=50_000)
    mode: str = Field(default="merge", pattern="^(merge|replace)$")


class SyllabusImportResult(BaseModel):
    chapters_created: int
    topics_created: int
    chapters_updated: int
    topics_updated: int
