from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    """
    Added ahead of Day 11 (auth), so quiz_attempts can reference user_id from the
    start instead of needing a migration to add the FK later.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Same reasoning as Topic.quiz_attempts — trust MySQL's ON DELETE CASCADE
    # instead of the ORM trying to null out a NOT NULL FK on user deletion.
    quiz_attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="user", passive_deletes=True
    )