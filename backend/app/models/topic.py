from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mirrors "does Qdrant have chunks for this topic_id" so GET /topics/{id}/status
    # (Day 4) can answer instantly without querying Qdrant on every request. Set to
    # True by the Day 3 ingestion worker once chunks are successfully upserted.
    has_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    chapter: Mapped["Chapter"] = relationship(back_populates="topics")
    syllabus_documents: Mapped[list["SyllabusDocument"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    generated_questions: Mapped[list["GeneratedQuestion"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    # passive_deletes=True: when a topic is deleted (e.g. via cascading delete
    # from its parent chapter/course), let MySQL's ON DELETE CASCADE on
    # quiz_attempts.topic_id handle removal — don't let the ORM try to UPDATE
    # quiz_attempts.topic_id to NULL first, which would fail against the
    # NOT NULL constraint on that column.
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="topic", passive_deletes=True
    )