"""Past papers found online or uploaded.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "past_papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("year", sa.String(20), nullable=True),
        sa.Column("page_url", sa.String(1000), nullable=True),
        sa.Column("file_url", sa.String(767), nullable=False),
        sa.Column("assets", sa.JSON(), nullable=True),
        sa.Column("stored_path", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="found"),
        sa.Column("ocr", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mcq_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mcq_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_id", "file_url", name="uq_past_paper_course_file"),
    )
    op.create_index("ix_past_papers_course_id", "past_papers", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_past_papers_course_id", table_name="past_papers")
    op.drop_table("past_papers")
