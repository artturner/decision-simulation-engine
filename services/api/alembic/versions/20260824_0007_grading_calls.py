"""add grading_calls usage ledger

One row per AI grading API call, attributed to the teacher who owns the
class roll, for monthly quota enforcement and cost visibility.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grading_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("play_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("class_roll_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["play_id"], ["plays.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["class_roll_id"], ["class_rolls.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_grading_calls_teacher_created",
        "grading_calls",
        ["teacher_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_grading_calls_teacher_created", table_name="grading_calls")
    op.drop_table("grading_calls")
