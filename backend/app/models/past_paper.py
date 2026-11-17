"""A past exam paper found online (PSC, NRB, the web) or uploaded by an admin."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

# found -> processing -> done | no_mcq | failed
PAPER_FOUND = "found"
PAPER_PROCESSING = "processing"
PAPER_DONE = "done"
PAPER_NO_MCQ = "no_mcq"
PAPER_FAILED = "failed"


class PastPaper(TimestampMixin, Base):
    __tablename__ = "past_papers"
    __table_args__ = (UniqueConstraint("course_id", "file_url", name="uq_past_paper_course_file"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # psc | nrb | web | upload
    year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    page_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # The paper itself: a PDF/image URL, or the page URL when the paper is a set of images on a page.
    file_url: Mapped[str] = mapped_column(String(767), nullable=False)
    assets: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # image/PDF URLs that make up the paper
    stored_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PAPER_FOUND)
    ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mcq_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mcq_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
