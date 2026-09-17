"""add student_claim_codes table

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-17

No backfill: rows are created lazily when the teacher first views a
roll's access codes — a code nobody has seen has no value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_claim_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "class_roll_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_rolls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_name", sa.String(length=500), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "claim_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.UniqueConstraint(
            "class_roll_id", "student_name", name="uq_claim_roll_student"
        ),
    )
    op.create_index(
        "ix_student_claim_codes_class_roll_id",
        "student_claim_codes",
        ["class_roll_id"],
    )
    op.create_index(
        "ix_student_claim_codes_code",
        "student_claim_codes",
        ["code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_student_claim_codes_code", table_name="student_claim_codes")
    op.drop_index(
        "ix_student_claim_codes_class_roll_id", table_name="student_claim_codes"
    )
    op.drop_table("student_claim_codes")
