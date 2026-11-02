"""Management tables: admins, audit_logs, and the 2.0 session table.

The legacy ``admin_sessions`` rows held only a username and an expiry and are all
long expired, so the table is rebuilt with the columns the cookie/CSRF pair needs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="admin", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_ip", sa.String(length=64), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admins")),
    )
    op.create_index(op.f("ix_admins_username"), "admins", ["username"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("actor_label", sa.String(length=64), server_default="system", nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("target_type", sa.String(length=32), server_default="", nullable=False),
        sa.Column("target_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("ip", sa.String(length=64), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["admins.id"], name=op.f("fk_audit_logs_actor_id_admins"), ondelete="SET NULL"
        ),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_created_action", "audit_logs", ["created_at", "action"])

    if "admin_sessions" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_index(op.f("ix_admin_sessions_id"), table_name="admin_sessions")
        op.drop_table("admin_sessions")

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=64), server_default="", nullable=False),
        sa.Column("csrf_token", sa.String(length=64), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("ip", sa.String(length=64), server_default="", nullable=False),
        sa.Column("user_agent", sa.String(length=200), server_default="", nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admins.id"], name=op.f("fk_admin_sessions_admin_id_admins"), ondelete="CASCADE"
        ),
    )
    op.create_index(op.f("ix_admin_sessions_admin_id"), "admin_sessions", ["admin_id"])
    op.create_index(op.f("ix_admin_sessions_username"), "admin_sessions", ["username"])
    op.create_index(op.f("ix_admin_sessions_expires_at"), "admin_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("admin_sessions")
    op.drop_table("audit_logs")
    op.drop_table("admins")
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_admin_sessions"),
    )
