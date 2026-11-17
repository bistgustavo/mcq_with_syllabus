"""Topic schemas: CRUD payloads, the enriched status view and the tree node."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.syllabus_document import SyllabusDocumentRead


class TopicCreate(BaseModel):
    """Payload for creating a topic under a chapter."""

    chapter_id: int
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class TopicUpdate(BaseModel):
    """Partial update of a topic."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class TopicRead(BaseModel):
    """Public representation of a topic."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    name: str
    description: str | None = None
    has_content: bool = False
    created_at: datetime | None = None


class TopicStatus(BaseModel):
    """Content/ingestion status of a topic, returned by GET /topics/{id}/status."""

    topic_id: int
    processing: bool = False
    has_content: bool
    has_web_content: bool = False
    chunk_count: int = 0
    question_count: int = 0
    documents: list[SyllabusDocumentRead] = Field(default_factory=list)


class TopicTree(TopicRead):
    """Topic node inside the course tree (adds the number of stored questions)."""

    question_count: int = 0


class TopicDetail(TopicRead):
    """Topic with its breadcrumb (chapter + course) for the topic page."""

    chapter_name: str
    course_id: int
    course_name: str
    question_count: int = 0
    question_count_by_difficulty: dict[str, int] = Field(default_factory=dict)
