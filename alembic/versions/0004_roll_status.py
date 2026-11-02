"""Roll results: void status, ownership, and per-activity number uniqueness.

``uq_roll_results_number_per_activity`` is *partial* (``WHERE status = 'valid'``) so a
voided row keeps its history while freeing the number for someone else to draw.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REBUILD = """
CREATE TABLE roll_results__new (
    id VARCHAR(36) NOT NULL,
    activity_id VARCHAR(32) NOT NULL,
    name VARCHAR(64) NOT NULL,
    number INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'valid',
    ip VARCHAR(64) NOT NULL DEFAULT '',
    timestamp DATETIME NOT NULL,
    void_reason VARCHAR(200) NOT NULL DEFAULT '',
    voided_at DATETIME,
    created_by_id INTEGER,
    CONSTRAINT pk_roll_results PRIMARY KEY (id),
    CONSTRAINT ck_roll_results_number_non_negative CHECK (number >= 0),
    CONSTRAINT fk_roll_results_activity_id_activities
        FOREIGN KEY (activity_id) REFERENCES activities (id) ON DELETE CASCADE,
    CONSTRAINT fk_roll_results_created_by_id_admins
        FOREIGN KEY (created_by_id) REFERENCES admins (id) ON DELETE SET NULL
)
"""

_COPY = """
INSERT INTO roll_results__new (id, activity_id, name, number, status, ip, timestamp)
SELECT id,
       activity_id,
       COALESCE(name, ''),
       COALESCE(number, 0),
       'valid',
       COALESCE(ip, ''),
       COALESCE(timestamp, '1970-01-01 00:00:00')
FROM roll_results
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(_REBUILD)
    bind.exec_driver_sql(_COPY)
    bind.exec_driver_sql("DROP TABLE roll_results")
    bind.exec_driver_sql("ALTER TABLE roll_results__new RENAME TO roll_results")

    op.create_index("ix_roll_results_activity_id", "roll_results", ["activity_id"])
    op.create_index("ix_roll_results_name", "roll_results", ["name"])
    op.create_index("ix_roll_results_status", "roll_results", ["status"])
    op.create_index("ix_roll_results_timestamp", "roll_results", ["timestamp"])
    op.create_index("ix_roll_results_created_by_id", "roll_results", ["created_by_id"])
    op.create_index("ix_roll_results_activity_status_number", "roll_results",
                   ["activity_id", "status", "number"])
    op.create_index(
        "uq_roll_results_number_per_activity",
        "roll_results",
        ["activity_id", "number"],
        unique=True,
        sqlite_where=sa.text("status = 'valid'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE roll_results__old (
            id VARCHAR NOT NULL,
            activity_id VARCHAR,
            name VARCHAR,
            number INTEGER,
            ip VARCHAR,
            timestamp DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY (activity_id) REFERENCES activities (id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO roll_results__old (id, activity_id, name, number, ip, timestamp)
        SELECT id, activity_id, name, number, ip, timestamp
        FROM roll_results WHERE status = 'valid'
        """
    )
    bind.exec_driver_sql("DROP TABLE roll_results")
    bind.exec_driver_sql("ALTER TABLE roll_results__old RENAME TO roll_results")
    op.create_index("ix_roll_results_name", "roll_results", ["name"])
    op.create_index("ix_roll_results_activity_id", "roll_results", ["activity_id"])
