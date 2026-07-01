"""add grading_difficulty to scenario_roll_assignments

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_roll_assignments",
        sa.Column(
            "grading_difficulty",
            sa.String(20),
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("scenario_roll_assignments", "grading_difficulty")
