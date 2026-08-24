"""add is_approved to users

New teacher accounts start unapproved and cannot use teacher endpoints
until an operator approves them. Existing accounts are grandfathered in.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Grandfather every account that existed before the approval gate.
    op.execute("UPDATE users SET is_approved = true")


def downgrade() -> None:
    op.drop_column("users", "is_approved")
