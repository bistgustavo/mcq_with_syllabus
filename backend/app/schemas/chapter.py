"""Chapter schemas: CRUD payloads and the tree node with nested topics."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.topic import TopicTree


class ChapterCreate(BaseModel):
    """Payload for creating a chapter under a course.

    ``order`` is optional; when omitted the API appends the chapter after the
    course's current last chapter.
    """

    course_id: int
    name: str = Field(..., min_length=1, max_length=255)
    order: int | None = Field(default=None, ge=0)
    weight: int = Field(default=0, ge=0, le=200)
    paper: str | None = Field(default=None, max_length=255)


class ChapterUpdate(BaseModel):
    """Partial update of a chapter."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    order: int | None = Field(default=None, ge=0)
    weight: int | None = Field(default=None, ge=0, le=200)
    paper: str | None = Field(default=None, max_length=255)


class ChapterRead(BaseModel):
    """Public representation of a chapter."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    name: str
    order: int
    weight: int = 0
    paper: str | None = None
    created_at: datetime | None = None


class ChapterTree(ChapterRead):
    """Chapter node inside the course tree, carrying its topics in id order."""

    topics: list[TopicTree] = Field(default_factory=list)
