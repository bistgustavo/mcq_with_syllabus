"""GeneratedQuestion ORM model: one multiple-choice question produced by an LLM for a topic."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from app.models.topic import Topic


class GeneratedQuestion(TimestampMixin, Base):
    """A stored MCQ with its four options, answer, explanation and provenance."""

    __tablename__ = "generated_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # exactly 4 strings
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-3
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # "ollama" | "groq" | "gemini"
    difficulty: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default="medium"
    )  # "easy" | "medium" | "hard"
    question_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Where the question came from, for display: e.g. "NRB AD 2081 Paper I", a URL, or a notes file.
    reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    topic: Mapped["Topic"] = relationship("Topic", back_populates="generated_questions")

    def __repr__(self) -> str:
        return f"<GeneratedQuestion id={self.id} topic_id={self.topic_id} source={self.source!r}>"
