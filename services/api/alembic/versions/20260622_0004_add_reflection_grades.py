"""add AI grading columns to reflections

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reflections", sa.Column("grade_total", sa.Integer(), nullable=True))
    op.add_column("reflections", sa.Column("grade_breakdown", JSONB(), nullable=True))
    op.add_column("reflections", sa.Column("feedback", sa.Text(), nullable=True))
    op.add_column(
        "reflections",
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reflections",
        sa.Column(
            "grade_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "reflections",
        sa.Column(
            "accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "reflections",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reflections",
        sa.Column("grader_model", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reflections", "grader_model")
    op.drop_column("reflections", "accepted_at")
    op.drop_column("reflections", "accepted")
    op.drop_column("reflections", "grade_attempts")
    op.drop_column("reflections", "graded_at")
    op.drop_column("reflections", "feedback")
    op.drop_column("reflections", "grade_breakdown")
    op.drop_column("reflections", "grade_total")
