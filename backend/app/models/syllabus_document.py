from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin

# Ingestion lifecycle of a document.
DOC_PENDING = "pending"
DOC_PROCESSING = "processing"
DOC_READY = "ready"
DOC_EMPTY = "empty"
DOC_FAILED = "failed"


class SyllabusDocument(Base, TimestampMixin):
    __tablename__ = "syllabus_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    # A document belongs to one topic, or (topic_id NULL) to a whole chapter:
    # chapter notes serve every topic of that chapter through semantic retrieval.
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Display name: the original upload filename, or "web:<url>" for web snippets.
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Name on disk inside UPLOAD_DIR/<topic_id>/ (unique, avoids overwrites). NULL for web snippets.
    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Matches Qdrant's payload "source_type": "upload" or "web_search".
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="upload")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DOC_PENDING, server_default=DOC_READY)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    topic: Mapped["Topic"] = relationship(back_populates="syllabus_documents")
