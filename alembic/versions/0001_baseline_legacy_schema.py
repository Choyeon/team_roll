"""Baseline: the pre-2.0 schema (activities, roll_results, admin_sessions).

Existing 1.x databases already match this shape, so ``app.db.migrate`` stamps
this revision instead of replaying it. Fresh databases run it and then continue
through the 2.0 revisions, so both paths land on identical DDL.

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()
    if "activities" not in tables:
        op.create_table(
            "activities",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("roll_min", sa.Integer(), server_default="1", nullable=True),
            sa.Column("roll_max", sa.Integer(), server_default="100", nullable=True),
            sa.Column("max_participations", sa.Integer(), server_default="1", nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
        )
        op.create_index(op.f("ix_activities_id"), "activities", ["id"])
        op.create_index(op.f("ix_activities_name"), "activities", ["name"])

    if "roll_results" not in tables:
        op.create_table(
            "roll_results",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("activity_id", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("number", sa.Integer(), nullable=True),
            sa.Column("ip", sa.String(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_roll_results")),
            sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], name="fk_legacy_roll_results_activity"),
        )
        op.create_index(op.f("ix_roll_results_id"), "roll_results", ["id"])
        op.create_index(op.f("ix_roll_results_name"), "roll_results", ["name"])
        op.create_index(op.f("ix_roll_results_activity_id"), "roll_results", ["activity_id"])

    if "admin_sessions" not in tables:
        op.create_table(
            "admin_sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("username", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        )
        op.create_index(op.f("ix_admin_sessions_id"), "admin_sessions", ["id"])


def downgrade() -> None:
    op.drop_table("admin_sessions")
    op.drop_table("roll_results")
    op.drop_table("activities")
