"""Timezone-aware clock helpers.

All persisted instants are UTC. SQLite has no timezone column type, so naive
datetimes read back from the database carry no offset; UTCDateTime normalises
both directions so application code never compares naive against aware values.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.engine import Dialect

UTC = UTC


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_naive_utc(value: datetime) -> datetime:
    return to_utc(value).replace(tzinfo=None)


class UTCDateTime(TypeDecorator):
    """Column type that stores naive UTC and returns aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return to_naive_utc(value)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return to_utc(value)
