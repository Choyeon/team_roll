"""Dashboard aggregates and activity statistics."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from sqlalchemy import Text, cast, distinct, func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models import Activity, ActivityStatus, AuditLog, RollResult, RollStatus

MAX_TREND_DAYS = 60
MAX_TZ_OFFSET_MINUTES = 14 * 60
DISTRIBUTION_BUCKETS = 10


def _day_expr(offset_minutes: int):
    """Bucket timestamps by the viewer's local day instead of UTC."""
    offset = max(-MAX_TZ_OFFSET_MINUTES, min(MAX_TZ_OFFSET_MINUTES, int(offset_minutes)))
    return func.date(cast(RollResult.timestamp, Text), f"{offset:+d} minutes")


def _local_today(offset_minutes: int) -> date:
    offset = max(-MAX_TZ_OFFSET_MINUTES, min(MAX_TZ_OFFSET_MINUTES, int(offset_minutes)))
    return (utc_now() + timedelta(minutes=offset)).date()


def kpis(db: Session, *, tz_offset_minutes: int = 0) -> dict[str, Any]:
    activity_row = db.execute(
        select(
            func.count(Activity.id),
            func.count(Activity.id).filter(Activity.status == ActivityStatus.ACTIVE),
            func.count(Activity.id).filter(Activity.status == ActivityStatus.ENDED),
        )
    ).one()

    roll_row = db.execute(
        select(
            func.count(RollResult.id),
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID),
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VOID),
            func.count(distinct(RollResult.name)).filter(RollResult.status == RollStatus.VALID),
        )
    ).one()

    today = _local_today(tz_offset_minutes)
    day = _day_expr(tz_offset_minutes)
    rolls_today = db.execute(
        select(func.count(RollResult.id)).where(day == today.isoformat())
    ).scalar_one()
    week_start = (today - timedelta(days=6)).isoformat()
    rolls_week = db.execute(
        select(func.count(RollResult.id)).where(day >= week_start)
    ).scalar_one()

    fills = db.execute(
        select(
            Activity.roll_min,
            Activity.roll_max,
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID).label("valid"),
        )
        .outerjoin(RollResult, RollResult.activity_id == Activity.id)
        .group_by(Activity.id)
    ).all()
    ratios = [row.valid / (row.roll_max - row.roll_min + 1) for row in fills if row.roll_max >= row.roll_min]

    return {
        "activities_total": int(activity_row[0] or 0),
        "activities_active": int(activity_row[1] or 0),
        "activities_ended": int(activity_row[2] or 0),
        "rolls_total": int(roll_row[0] or 0),
        "rolls_valid": int(roll_row[1] or 0),
        "rolls_void": int(roll_row[2] or 0),
        "participants_unique": int(roll_row[3] or 0),
        "rolls_today": int(rolls_today or 0),
        "rolls_last_7_days": int(rolls_week or 0),
        "avg_fill_rate": round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        "median_fill_rate": round(median(ratios), 4) if ratios else 0.0,
    }


def trend(db: Session, *, days: int = 14, tz_offset_minutes: int = 0) -> list[dict]:
    days = max(1, min(MAX_TREND_DAYS, days))
    today = _local_today(tz_offset_minutes)
    start = today - timedelta(days=days - 1)
    day = _day_expr(tz_offset_minutes)
    rows = db.execute(
        select(day.label("day"), func.count(RollResult.id).label("rolls"))
        .where(day >= start.isoformat())
        .group_by("day")
    ).all()
    counts = {row.day: int(row.rolls or 0) for row in rows}
    return [
        {
            "day": bucket.isoformat(),
            "rolls": counts.get(bucket.isoformat(), 0),
        }
        for bucket in (start + timedelta(days=offset) for offset in range(days))
    ]


def top_activities(db: Session, *, limit: int = 5) -> list[dict]:
    rows = db.execute(
        select(
            Activity.id,
            Activity.name,
            Activity.status,
            Activity.roll_min,
            Activity.roll_max,
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID).label("valid"),
            func.max(RollResult.number).filter(RollResult.status == RollStatus.VALID).label("top"),
        )
        .outerjoin(RollResult, RollResult.activity_id == Activity.id)
        .group_by(Activity.id)
        .order_by(func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID).desc(), Activity.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "status": row.status.value,
            "roll_count": int(row.valid or 0),
            "top_number": row.top,
            "completion": round((row.valid or 0) / (row.roll_max - row.roll_min + 1), 4),
        }
        for row in rows
    ]


def status_breakdown(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Activity.status,
            func.count(func.distinct(Activity.id)),
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID),
        )
        .outerjoin(RollResult, RollResult.activity_id == Activity.id)
        .group_by(Activity.status)
    ).all()
    return [
        {"status": status.value, "activities": int(total or 0), "rolls": int(rolls or 0)}
        for status, total, rolls in rows
    ]


def recent_rolls(db: Session, *, limit: int = 8) -> list[dict]:
    rows = db.execute(
        select(RollResult, Activity.name)
        .join(Activity, Activity.id == RollResult.activity_id)
        .where(RollResult.status == RollStatus.VALID)
        .order_by(RollResult.timestamp.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": roll.id,
            "name": roll.name,
            "number": roll.number,
            "activity_id": roll.activity_id,
            "activity_name": activity_name,
            "status": roll.status.value,
            "timestamp": roll.timestamp.isoformat(),
        }
        for roll, activity_name in rows
    ]


def recent_audit(db: Session, *, limit: int = 8) -> list[dict]:
    rows = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "action": row.action,
            "actor_label": row.actor_label,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "ip": row.ip,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def dashboard(db: Session, *, tz_offset_minutes: int = 0, trend_days: int = 14, live_connections: int = 0) -> dict:
    return {
        "generated_at": utc_now().isoformat(),
        "kpis": kpis(db, tz_offset_minutes=tz_offset_minutes),
        "trend": trend(db, days=trend_days, tz_offset_minutes=tz_offset_minutes),
        "top_activities": top_activities(db),
        "status_breakdown": status_breakdown(db),
        "live_connections": live_connections,
        "recent_rolls": recent_rolls(db),
        "recent_audit": recent_audit(db),
    }


def activity_stats(db: Session, activity: Activity) -> dict:
    numbers = list(
        db.execute(
            select(RollResult.number).where(
                RollResult.activity_id == activity.id, RollResult.status == RollStatus.VALID
            )
        ).scalars()
    )
    total = activity.range_size
    taken = len(numbers)
    buckets = [0] * DISTRIBUTION_BUCKETS
    if taken:
        width = max(1, total // DISTRIBUTION_BUCKETS)
        for number in numbers:
            index = min(DISTRIBUTION_BUCKETS - 1, (number - activity.roll_min) // max(1, width))
            buckets[index] += 1
    return {
        "activity_id": activity.id,
        "range": [activity.roll_min, activity.roll_max],
        "range_size": total,
        "taken": taken,
        "remaining": max(0, total - taken),
        "completion": round(taken / total, 4) if total else 0.0,
        "mean": round(sum(numbers) / taken, 2) if taken else None,
        "median": median(numbers) if taken else None,
        "min": min(numbers) if taken else None,
        "max": max(numbers) if taken else None,
        "distribution": buckets,
        "distribution_labels": _bucket_labels(activity.roll_min, total),
    }


def _bucket_labels(roll_min: int, total: int) -> list[str]:
    width = max(1, total // DISTRIBUTION_BUCKETS)
    return [str(roll_min + index * width) for index in range(DISTRIBUTION_BUCKETS)]
