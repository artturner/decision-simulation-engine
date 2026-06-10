"""users, class rolls, scenario-roll assignments

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-09

Adds multi-teacher support and class roll infrastructure:

  users                     — teacher / admin accounts (UUID matches Supabase Auth sub)
  class_rolls               — reusable named lists of student names owned by a teacher
  scenario_roll_assignments — many-to-many between scenarios and rolls with visibility flag

Also adds two nullable FK columns to existing tables:
  scenarios.owner_id   → users.id        (SET NULL on user delete)
  plays.class_roll_id  → class_rolls.id  (SET NULL on roll delete)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enum type for user roles
    # ------------------------------------------------------------------
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE userrole AS ENUM ('teacher', 'admin'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$"
    ))

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Matches the Supabase Auth user UUID (sub claim)",
        ),
        sa.Column("email", sa.String(500), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="userrole", create_type=False),
            nullable=False,
            server_default="teacher",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------
    # class_rolls
    # ------------------------------------------------------------------
    op.create_table(
        "class_rolls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column(
            "student_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment='Ordered list of canonical student names, e.g. ["Last, First", ...]',
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_class_rolls_owner_id", "class_rolls", ["owner_id"])

    # ------------------------------------------------------------------
    # Add owner_id to scenarios (nullable — existing rows get NULL)
    # ------------------------------------------------------------------
    op.add_column(
        "scenarios",
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Teacher who owns this scenario; NULL for legacy/imported scenarios",
        ),
    )
    op.create_foreign_key(
        "fk_scenarios_owner_id",
        "scenarios",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_scenarios_owner_id", "scenarios", ["owner_id"])

    # ------------------------------------------------------------------
    # Add class_roll_id to plays (nullable — existing rows get NULL)
    # ------------------------------------------------------------------
    op.add_column(
        "plays",
        sa.Column(
            "class_roll_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Set when play was started via class picker; NULL for direct links",
        ),
    )
    op.create_foreign_key(
        "fk_plays_class_roll_id",
        "plays",
        "class_rolls",
        ["class_roll_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_plays_class_roll_id", "plays", ["class_roll_id"])

    # ------------------------------------------------------------------
    # scenario_roll_assignments
    # ------------------------------------------------------------------
    op.create_table(
        "scenario_roll_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_roll_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "visible",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether the scenario appears in this roll's class picker",
        ),
        sa.Column(
            "sort_order",
            sa.Integer,
            nullable=True,
            comment="Display order within the picker; lower numbers appear first",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["scenarios.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["class_roll_id"], ["class_rolls.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_id",
            "class_roll_id",
            name="uq_scenario_roll_assignments_scenario_roll",
        ),
    )
    op.create_index(
        "ix_scenario_roll_assignments_scenario_id",
        "scenario_roll_assignments",
        ["scenario_id"],
    )
    op.create_index(
        "ix_scenario_roll_assignments_class_roll_id",
        "scenario_roll_assignments",
        ["class_roll_id"],
    )


def downgrade() -> None:
    op.drop_table("scenario_roll_assignments")

    op.drop_index("ix_plays_class_roll_id", table_name="plays")
    op.drop_constraint("fk_plays_class_roll_id", "plays", type_="foreignkey")
    op.drop_column("plays", "class_roll_id")

    op.drop_index("ix_scenarios_owner_id", table_name="scenarios")
    op.drop_constraint("fk_scenarios_owner_id", "scenarios", type_="foreignkey")
    op.drop_column("scenarios", "owner_id")

    op.drop_table("class_rolls")
    op.drop_table("users")

    op.execute(sa.text("DROP TYPE IF EXISTS userrole"))
