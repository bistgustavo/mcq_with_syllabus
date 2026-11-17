"""Question provenance (reference) for past papers, notes and web sources.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("generated_questions", sa.Column("reference", sa.String(500), nullable=True))
    op.create_index("ix_generated_questions_source", "generated_questions", ["source"])


def downgrade() -> None:
    op.drop_index("ix_generated_questions_source", table_name="generated_questions")
    op.drop_column("generated_questions", "reference")
