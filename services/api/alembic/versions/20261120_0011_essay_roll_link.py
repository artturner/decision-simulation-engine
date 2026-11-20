"""link class rolls to essay-grader classes

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-20

Access codes live here, so an essays-only class needs a roll in this
app to hold them. ``essay_roll_id`` records which essay class a roll
issues codes for; ``mirrors_essay_roll`` marks rolls created for that
purpose, whose roster then follows the essay class.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "class_rolls",
        sa.Column("essay_roll_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "class_rolls",
        sa.Column(
            "mirrors_essay_roll",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_unique_constraint(
        "class_rolls_essay_roll_id_key", "class_rolls", ["essay_roll_id"]
    )


def downgrade() -> None:
    op.drop_constraint("class_rolls_essay_roll_id_key", "class_rolls", type_="unique")
    op.drop_column("class_rolls", "mirrors_essay_roll")
    op.drop_column("class_rolls", "essay_roll_id")
