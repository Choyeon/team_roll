"""Activity lifecycle: status machine, timestamps, ownership, and rules tightened.

SQLite cannot add non-nullable columns, CHECK constraints, or a partial index in
place, so ``activities`` is rebuilt with the 2.0 shape and the rows are copied in
the same statement. ``is_active`` is folded into ``status`` first: an inactive
legacy activity becomes ``ended`` because its leaderboard is already final.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REBUILD = """
CREATE TABLE activities__new (
    id VARCHAR(32) NOT NULL,
    name VARCHAR(80) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    roll_min INTEGER NOT NULL DEFAULT 1,
    roll_max INTEGER NOT NULL DEFAULT 100,
    max_participations INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    started_at DATETIME,
    ended_at DATETIME,
    created_by_id INTEGER,
    CONSTRAINT pk_activities PRIMARY KEY (id),
    CONSTRAINT ck_activities_roll_range_ordered CHECK (roll_max >= roll_min),
    CONSTRAINT fk_activities_created_by_id_admins
        FOREIGN KEY (created_by_id) REFERENCES admins (id) ON DELETE SET NULL
)
"""

_COPY = """
INSERT INTO activities__new (
    id, name, description, status, roll_min, roll_max, max_participations,
    created_at, updated_at, started_at, ended_at, created_by_id
)
SELECT
    id,
    COALESCE(name, ''),
    COALESCE(description, ''),
    CASE WHEN COALESCE(is_active, 1) = 0 THEN 'ended' ELSE 'active' END,
    COALESCE(roll_min, 1),
    COALESCE(roll_max, 100),
    COALESCE(max_participations, 1),
    COALESCE(created_at, '1970-01-01 00:00:00'),
    COALESCE(created_at, '1970-01-01 00:00:00'),
    COALESCE(created_at, '1970-01-01 00:00:00'),
    CASE WHEN COALESCE(is_active, 1) = 0 THEN created_at ELSE NULL END,
    NULL
FROM activities
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(_REBUILD)
    bind.exec_driver_sql(_COPY)
    bind.exec_driver_sql("DROP TABLE activities")
    bind.exec_driver_sql("ALTER TABLE activities__new RENAME TO activities")
    op.create_index("ix_activities_status", "activities", ["status"])
    op.create_index("ix_activities_name", "activities", ["name"])
    op.create_index("ix_activities_created_by_id", "activities", ["created_by_id"])


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE activities__old (
            id VARCHAR NOT NULL,
            name VARCHAR,
            description TEXT,
            created_at DATETIME,
            is_active BOOLEAN,
            roll_min INTEGER DEFAULT 1,
            roll_max INTEGER DEFAULT 100,
            max_participations INTEGER DEFAULT 1,
            PRIMARY KEY (id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO activities__old (id, name, description, created_at, is_active,
                                    roll_min, roll_max, max_participations)
        SELECT id, name, description, created_at,
               CASE WHEN status = 'ended' THEN 0 ELSE 1 END,
               roll_min, roll_max, max_participations
        FROM activities
        """
    )
    bind.exec_driver_sql("DROP TABLE activities")
    bind.exec_driver_sql("ALTER TABLE activities__old RENAME TO activities")
    op.create_index("ix_activities_name", "activities", ["name"])
