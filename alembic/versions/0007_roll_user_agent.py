"""Browser signature on roll results.

The public board never sees it; the admin roll table uses it to tell apart
players who share one exit IP and to spot scripted submissions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "roll_results",
        sa.Column("user_agent", sa.String(200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    with op.batch_alter_table("roll_results") as batch_op:
        batch_op.drop_column("user_agent")
