from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Exam pattern used for mock tests and to steer question style.
    exam_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "NRB Computer Officer"
    exam_question_count: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    exam_duration_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    negative_marking: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)  # fraction of a mark lost per wrong answer
    pass_percent: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # Marking scheme from the syllabus.
    marks_per_question: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    # "per_paper": every paper must reach pass_percent (NRB). "overall": the combined score does (Lok Sewa Paper I).
    pass_rule: Mapped[str] = mapped_column(String(20), default="per_paper", nullable=False)
    exam_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )