"""Rewind pre-2.0 naive timestamps to real UTC.

The 1.x code wrote ``datetime.now()`` (server-local, naive). 2.0 stores naive UTC, so
the historical rows are shifted back by ``LEGACY_LOCAL_OFFSET_MINUTES`` (default 480,
i.e. the UTC+8 machine that produced them). Admins, sessions and audit logs created by
this migration are already UTC and are left alone.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _offset_minutes(sign: int) -> int:
    from app.core.config import get_settings

    return sign * get_settings().legacy_local_offset_minutes


def _shift(table: str, columns: list[str], minutes: int) -> None:
    modifier = f"'{minutes:+d} minutes'"
    assignments = ", ".join(f"{name} = datetime({name}, {modifier})" for name in columns)
    op.get_bind().exec_driver_sql(f"UPDATE {table} SET {assignments}")


def upgrade() -> None:
    minutes = _offset_minutes(-1)
    _shift("activities", ["created_at", "updated_at", "started_at", "ended_at"], minutes)
    _shift("roll_results", ["timestamp"], minutes)


def downgrade() -> None:
    minutes = _offset_minutes(1)
    _shift("activities", ["created_at", "updated_at", "started_at", "ended_at"], minutes)
    _shift("roll_results", ["timestamp"], minutes)
