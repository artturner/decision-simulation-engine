"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-19

Creates all tables for the branching scenarios MVP:
  scenarios, scenario_versions, plays, events, reflections

Also creates two native Postgres enum types:
  versionstatus  (draft | published | archived)
  eventtype      (start | view_scene | choose | auto_advance |
                  conditional_advance | go_back | complete)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enum types — must be created before any table that uses them
    # ------------------------------------------------------------------

    # Use a DO block so creation is idempotent (Postgres has no
    # CREATE TYPE IF NOT EXISTS syntax).
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE versionstatus AS ENUM ('draft', 'published', 'archived'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$"
    ))
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE eventtype AS ENUM ("
        "'start', 'view_scene', 'choose', 'auto_advance', "
        "'conditional_advance', 'go_back', 'complete'"
        "); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$"
    ))

    # ------------------------------------------------------------------
    # scenarios
    # ------------------------------------------------------------------

    op.create_table(
        "scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column(
            "description",
            sa.Text,
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenarios_slug", "scenarios", ["slug"], unique=True)

    # ------------------------------------------------------------------
    # scenario_versions
    # ------------------------------------------------------------------

    op.create_table(
        "scenario_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="versionstatus", create_type=False),
            nullable=False,
        ),
        sa.Column("scenario_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["scenarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scenario_id",
            "version_number",
            name="uq_scenario_versions_scenario_version",
        ),
    )
    op.create_index(
        "ix_scenario_versions_scenario_id",
        "scenario_versions",
        ["scenario_id"],
    )
    op.create_index(
        "ix_scenario_versions_status",
        "scenario_versions",
        ["status"],
    )

    # ------------------------------------------------------------------
    # plays
    # ------------------------------------------------------------------

    op.create_table(
        "plays",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learner_label", sa.String(500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("outcome", sa.String(200), nullable=True),
        sa.Column("outcome_message", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["scenario_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plays_scenario_version_id",
        "plays",
        ["scenario_version_id"],
    )

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("play_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(name="eventtype", create_type=False),
            nullable=False,
        ),
        sa.Column("scene_id", sa.String(200), nullable=True),
        sa.Column("choice_index", sa.Integer, nullable=True),
        sa.Column("choice_text", sa.Text, nullable=True),
        sa.Column("next_scene_id", sa.String(200), nullable=True),
        sa.Column("delta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["play_id"], ["plays.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("play_id", "seq", name="uq_events_play_seq"),
    )
    op.create_index("ix_events_play_id_seq", "events", ["play_id", "seq"])

    # ------------------------------------------------------------------
    # reflections
    # ------------------------------------------------------------------

    op.create_table(
        "reflections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("play_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("student_name", sa.String(500), nullable=True),
        sa.Column(
            "responses_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["play_id"], ["plays.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("play_id", name="uq_reflections_play_id"),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("reflections")
    op.drop_table("events")
    op.drop_table("plays")
    op.drop_table("scenario_versions")
    op.drop_table("scenarios")

    # Drop enum types last (tables that reference them are already gone)
    op.execute(sa.text("DROP TYPE IF EXISTS eventtype"))
    op.execute(sa.text("DROP TYPE IF EXISTS versionstatus"))
