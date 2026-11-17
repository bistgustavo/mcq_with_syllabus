"""Marking scheme on courses; per-paper sections and results on exam attempts.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("marks_per_question", sa.Float(), nullable=False, server_default="1"))
    op.add_column("courses", sa.Column("pass_rule", sa.String(20), nullable=False, server_default="per_paper"))
    op.add_column("exam_attempts", sa.Column("marks_per_question", sa.Float(), nullable=False, server_default="1"))
    op.add_column("exam_attempts", sa.Column("pass_rule", sa.String(20), nullable=False, server_default="per_paper"))
    op.add_column("exam_attempts", sa.Column("sections", sa.JSON(), nullable=True))
    op.add_column("exam_attempts", sa.Column("section_results", sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in ("section_results", "sections", "pass_rule", "marks_per_question"):
        op.drop_column("exam_attempts", col)
    op.drop_column("courses", "pass_rule")
    op.drop_column("courses", "marks_per_question")
