"""Platform features: admin flag, document ingestion status, quiz metadata, extra indexes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Existing installs: promote the earliest account so someone can manage content.
    op.execute("UPDATE users SET is_admin = 1 WHERE id = (SELECT id FROM (SELECT MIN(id) AS id FROM users) AS t)")

    op.add_column("syllabus_documents", sa.Column("stored_filename", sa.String(255), nullable=True))
    # Pre-existing rows were already ingested by the old pipeline → "ready".
    op.add_column("syllabus_documents", sa.Column("status", sa.String(20), nullable=False, server_default="ready"))
    op.add_column("syllabus_documents", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("syllabus_documents", sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("syllabus_documents", sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("syllabus_documents", sa.Column("task_id", sa.String(64), nullable=True))
    op.add_column("syllabus_documents", sa.Column("error", sa.Text(), nullable=True))

    op.add_column("quiz_attempts", sa.Column("difficulty", sa.String(20), nullable=True))
    op.add_column("quiz_attempts", sa.Column("duration_seconds", sa.Integer(), nullable=True))

    op.add_column("courses", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("topics", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("topics", "description")
    op.drop_column("courses", "is_published")
    op.drop_column("quiz_attempts", "duration_seconds")
    op.drop_column("quiz_attempts", "difficulty")
    for col in ("error", "task_id", "file_size", "page_count", "chunk_count", "status", "stored_filename"):
        op.drop_column("syllabus_documents", col)
    op.drop_column("users", "is_admin")
