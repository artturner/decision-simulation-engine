"""add reflection_attempts history table

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reflection_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reflection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reflections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("responses_json", postgresql.JSONB(), nullable=False),
        sa.Column("grade_total", sa.Integer(), nullable=False),
        sa.Column("grade_breakdown", postgresql.JSONB(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("grader_model", sa.String(length=100), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "reflection_id",
            "attempt_number",
            name="uq_reflection_attempts_reflection_attempt",
        ),
    )
    op.create_index(
        "ix_reflection_attempts_reflection_id",
        "reflection_attempts",
        ["reflection_id"],
    )

    # Backfill: materialize each already-graded reflection's current grade as
    # its latest attempt, so best-of reporting starts with a complete history.
    op.execute(
        """
        INSERT INTO reflection_attempts
            (id, reflection_id, attempt_number, responses_json, grade_total,
             grade_breakdown, feedback, grader_model, graded_at)
        SELECT gen_random_uuid(),
               id,
               GREATEST(COALESCE(grade_attempts, 1), 1),
               responses_json,
               grade_total,
               COALESCE(grade_breakdown, '{}'::jsonb),
               feedback,
               grader_model,
               COALESCE(graded_at, now())
        FROM reflections
        WHERE grade_total IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reflection_attempts_reflection_id", table_name="reflection_attempts"
    )
    op.drop_table("reflection_attempts")
