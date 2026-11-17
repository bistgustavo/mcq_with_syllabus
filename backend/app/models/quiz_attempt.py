"""QuizAttempt ORM model: one quiz taken by a user on a topic."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from app.models.topic import Topic
    from app.models.user import User


class QuizAttempt(TimestampMixin, Base):
    """A scored quiz attempt: which questions were asked, what was answered and the score."""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    question_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    answers: Mapped[list[int | None] | None] = mapped_column(JSON, nullable=True)  # chosen index per question
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="quiz_attempts")
    topic: Mapped["Topic"] = relationship("Topic", back_populates="quiz_attempts")

    def __repr__(self) -> str:
        return f"<QuizAttempt id={self.id} user_id={self.user_id} topic_id={self.topic_id} score={self.score}/{self.total}>"
