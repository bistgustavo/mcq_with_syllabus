"""Schemas for syllabus documents (uploaded PDFs and persisted web snippets)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SyllabusDocumentCreate(BaseModel):
    """Payload used internally when recording a new document for a topic."""

    topic_id: int
    filename: str = Field(..., min_length=1, max_length=500)
    source_type: str = Field(default="upload", pattern="^(upload|web_search)$")


class SyllabusDocumentRead(BaseModel):
    """Public representation of a syllabus document."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int | None = None
    chapter_id: int | None = None
    filename: str
    source_type: str
    status: str = "ready"
    chunk_count: int = 0
    page_count: int = 0
    file_size: int = 0
    error: str | None = None
    task_id: str | None = None
    created_at: datetime | None = None


class UploadResponse(BaseModel):
    """Body returned (HTTP 202) after a PDF upload has been queued for ingestion."""

    message: str
    task_id: str
    document: SyllabusDocumentRead
