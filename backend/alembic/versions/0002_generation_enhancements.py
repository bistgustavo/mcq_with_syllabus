"""Generation enhancements: difficulty + question_hash on generated_questions, answers on quiz_attempts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the difficulty/question_hash columns (+ index) and the answers column."""
    op.add_column(
        "generated_questions",
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
    )
    op.add_column(
        "generated_questions",
        sa.Column("question_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_generated_questions_question_hash",
        "generated_questions",
        ["question_hash"],
        unique=False,
    )
    op.add_column(
        "quiz_attempts",
        sa.Column("answers", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove the columns and index added in ``upgrade``."""
    op.drop_column("quiz_attempts", "answers")
    op.drop_index("ix_generated_questions_question_hash", table_name="generated_questions")
    op.drop_column("generated_questions", "question_hash")
    op.drop_column("generated_questions", "difficulty")
