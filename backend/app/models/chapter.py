from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class Chapter(Base, TimestampMixin):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Number of questions this chapter contributes to a full mock paper.
    # 0 = share the paper proportionally among chapters without a weight.
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Exam paper this chapter belongs to (e.g. "Paper I — Information Technology I").
    # NULL for single-paper courses. Mock tests can be taken per paper.
    paper: Mapped[str | None] = mapped_column(String(255), nullable=True)

    course: Mapped["Course"] = relationship(back_populates="chapters")
    topics: Mapped[list["Topic"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )