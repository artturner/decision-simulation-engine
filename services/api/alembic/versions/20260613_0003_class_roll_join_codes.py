"""add join codes to class rolls

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-13
"""

from __future__ import annotations

import secrets
import string

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_ALPHABET = string.ascii_uppercase + string.digits


def _join_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


def upgrade() -> None:
    op.add_column("class_rolls", sa.Column("join_code", sa.String(16), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM class_rolls")).mappings().all()
    used: set[str] = set()
    for row in rows:
        code = _join_code()
        while code in used:
            code = _join_code()
        used.add(code)
        conn.execute(
            sa.text("UPDATE class_rolls SET join_code = :code WHERE id = :id"),
            {"code": code, "id": row["id"]},
        )

    op.alter_column("class_rolls", "join_code", existing_type=sa.String(16), nullable=False)
    op.create_index("ix_class_rolls_join_code", "class_rolls", ["join_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_class_rolls_join_code", table_name="class_rolls")
    op.drop_column("class_rolls", "join_code")
