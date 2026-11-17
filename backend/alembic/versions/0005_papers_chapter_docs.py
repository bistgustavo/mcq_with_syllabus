"""Exam papers within a course; chapter-level documents.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chapters", sa.Column("paper", sa.String(255), nullable=True))
    op.add_column("exam_attempts", sa.Column("paper", sa.String(255), nullable=True))
    op.alter_column("syllabus_documents", "topic_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("syllabus_documents", sa.Column("chapter_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_syllabus_documents_chapter_id", "syllabus_documents", "chapters", ["chapter_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_syllabus_documents_chapter_id", "syllabus_documents", ["chapter_id"])


def downgrade() -> None:
    op.drop_index("ix_syllabus_documents_chapter_id", table_name="syllabus_documents")
    op.drop_constraint("fk_syllabus_documents_chapter_id", "syllabus_documents", type_="foreignkey")
    op.drop_column("syllabus_documents", "chapter_id")
    op.alter_column("syllabus_documents", "topic_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("exam_attempts", "paper")
    op.drop_column("chapters", "paper")
