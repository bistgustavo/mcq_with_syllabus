"""Mock exam attempts: a timed, paper-style test across a whole course."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

EXAM_IN_PROGRESS = "in_progress"
EXAM_SUBMITTED = "submitted"


class ExamAttempt(TimestampMixin, Base):
    __tablename__ = "exam_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=EXAM_IN_PROGRESS)
    paper: Mapped[str | None] = mapped_column(String(255), nullable=True)  # NULL = full exam (all papers)

    question_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    answers: Mapped[list[int | None] | None] = mapped_column(JSON, nullable=True)
    flagged: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_marking: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pass_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    marks_per_question: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    pass_rule: Mapped[str] = mapped_column(String(20), nullable=False, default="per_paper")
    # [{"paper", "start", "count", "minutes"}] — question index ranges per paper section.
    sections: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    section_results: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    chapter_breakdown: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
