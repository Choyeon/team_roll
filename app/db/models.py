"""ORM models.

Column names for ``activities`` / ``roll_results`` intentionally match the
pre-2.0 schema so the Alembic baseline migrates in place instead of rebuilding
tables that already hold real roll history.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import UTCDateTime, utc_now
from app.db.base import Base


class ActivityStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class RollStatus(str, enum.Enum):
    VALID = "valid"
    VOID = "void"


class AdminRole(str, enum.Enum):
    SUPER = "super"
    ADMIN = "admin"
    VIEWER = "viewer"


def _enum(enum_cls: type[enum.Enum]) -> SAEnum:
    """Persist the enum *value* (``active``) instead of the member name.

    ``create_constraint=False`` keeps the DDL in sync with the hand-written
    Alembic revisions, which store these columns as plain VARCHAR.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=16,
        create_constraint=False,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(_enum(AdminRole), default=AdminRole.ADMIN, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now, nullable=False)

    sessions: Mapped[list[AdminSession]] = relationship(back_populates="admin", cascade="all, delete-orphan")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (CheckConstraint("roll_max >= roll_min", name="roll_range_ordered"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ActivityStatus] = mapped_column(
        _enum(ActivityStatus), default=ActivityStatus.ACTIVE, nullable=False, index=True
    )

    roll_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    roll_max: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_participations: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Distinct participant names allowed; 0 means unlimited.
    max_participants: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True
    )

    roll_results: Mapped[list[RollResult]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", passive_deletes=True
    )
    created_by: Mapped[Admin | None] = relationship(foreign_keys=[created_by_id])

    @property
    def range_size(self) -> int:
        return self.roll_max - self.roll_min + 1


class RollResult(Base):
    __tablename__ = "roll_results"
    __table_args__ = (
        CheckConstraint("number >= 0", name="number_non_negative"),
        Index("uq_roll_results_number_per_activity", "activity_id", "number", unique=True,
              sqlite_where=text("status = 'valid'")),
        Index("ix_roll_results_activity_status_number", "activity_id", "status", "number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    activity_id: Mapped[str] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RollStatus] = mapped_column(
        _enum(RollStatus), default=RollStatus.VALID, nullable=False, index=True
    )
    ip: Mapped[str] = mapped_column(String(64), default="")
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False, index=True)

    void_reason: Mapped[str] = mapped_column(String(200), default="")
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True
    )

    activity: Mapped[Activity] = relationship(back_populates="roll_results")
    created_by: Mapped[Admin | None] = relationship(foreign_keys=[created_by_id])


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    admin: Mapped[Admin | None] = relationship(back_populates="sessions")

    @property
    def is_expired(self) -> bool:
        return utc_now() > self.expires_at


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created_action", "created_at", "action"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor_label: Mapped[str] = mapped_column(String(64), default="system")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False, index=True)
