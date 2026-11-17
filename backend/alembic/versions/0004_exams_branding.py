"""Exam pattern on courses, chapter weights, mock exam attempts, app settings.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("exam_name", sa.String(255), nullable=True))
    op.add_column("courses", sa.Column("exam_question_count", sa.Integer(), nullable=False, server_default="50"))
    op.add_column("courses", sa.Column("exam_duration_minutes", sa.Integer(), nullable=False, server_default="45"))
    op.add_column("courses", sa.Column("negative_marking", sa.Float(), nullable=False, server_default="0.2"))
    op.add_column("courses", sa.Column("pass_percent", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("courses", sa.Column("exam_instructions", sa.Text(), nullable=True))
    op.add_column("chapters", sa.Column("weight", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("question_ids", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("flagged", sa.JSON(), nullable=True),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("negative_marking", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pass_percent", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wrong", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("chapter_breakdown", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_attempts_user_id", "exam_attempts", ["user_id"])
    op.create_index("ix_exam_attempts_course_id", "exam_attempts", ["course_id"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_exam_attempts_course_id", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_user_id", table_name="exam_attempts")
    op.drop_table("exam_attempts")
    op.drop_column("chapters", "weight")
    for col in ("exam_instructions", "pass_percent", "negative_marking", "exam_duration_minutes", "exam_question_count", "exam_name"):
        op.drop_column("courses", col)
