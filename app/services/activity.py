"""Activity lifecycle: listing with aggregates, creation, rules editing, status, deletion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.security import generate_activity_id
from app.core.time import utc_now
from app.db.models import Activity, ActivityStatus, RollResult, RollStatus
from app.schemas.activity import ActivityInput, ActivityStatusUpdate, ActivityUpdate
from app.services import audit

TERMINAL_STATUSES = {ActivityStatus.ENDED}


@dataclass(frozen=True)
class RollStats:
    roll_count: int = 0
    void_count: int = 0
    participants: int = 0
    top_number: int | None = None


def stats_for(db: Session, activity_ids: list[str]) -> dict[str, RollStats]:
    """One aggregate query for the whole page instead of N+1 per-activity queries."""
    if not activity_ids:
        return {}
    rows = db.execute(
        select(
            RollResult.activity_id,
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID).label("valid"),
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VOID).label("void"),
            func.count(distinct(RollResult.name)).filter(RollResult.status == RollStatus.VALID).label("people"),
            func.max(RollResult.number).filter(RollResult.status == RollStatus.VALID).label("top"),
        )
        .where(RollResult.activity_id.in_(activity_ids))
        .group_by(RollResult.activity_id)
    ).all()
    return {
        row.activity_id: RollStats(
            roll_count=row.valid or 0,
            void_count=row.void or 0,
            participants=row.people or 0,
            top_number=row.top,
        )
        for row in rows
    }


def serialize(activity: Activity, stats: RollStats, *, admin_view: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": activity.id,
        "name": activity.name,
        "description": activity.description or "",
        "status": activity.status,
        "roll_min": activity.roll_min,
        "roll_max": activity.roll_max,
        "max_participations": activity.max_participations,
        "max_participants": activity.max_participants,
        "created_at": activity.created_at,
        "started_at": activity.started_at,
        "ended_at": activity.ended_at,
        "roll_count": stats.roll_count,
        "participants": stats.participants,
        "remaining_numbers": max(0, activity.range_size - stats.roll_count),
        "top_number": stats.top_number,
    }
    if admin_view:
        payload["updated_at"] = activity.updated_at
        payload["created_by"] = activity_created_by(activity)
        payload["void_count"] = stats.void_count
    return payload


def activity_created_by(activity: Activity) -> str:
    if activity.created_by is None:
        return ""
    return activity.created_by.username


def get_or_404(db: Session, activity_id: str) -> Activity:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise NotFound("活动不存在或已被删除")
    return activity


def list_page(
    db: Session,
    *,
    q: str = "",
    status: ActivityStatus | None = None,
    only_public: bool = False,
    page: int = 1,
    page_size: int = 20,
    admin_view: bool = False,
) -> tuple[list[dict], int]:
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(or_(Activity.name.like(like), Activity.description.like(like), Activity.id == q))
    if status is not None:
        filters.append(Activity.status == status)
    # 前台默认不出已结束的活动，但明确按状态筛选时要能翻出来，
    # 否则列表页的“已结束”标签页永远是空的。
    if only_public and status is None:
        filters.append(Activity.status != ActivityStatus.ENDED)

    total = db.execute(select(func.count(Activity.id)).where(*filters)).scalar_one()
    activities = list(
        db.execute(
            select(Activity)
            .where(*filters)
            .order_by(Activity.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    stats = stats_for(db, [activity.id for activity in activities])
    return [
        serialize(activity, stats.get(activity.id, RollStats()), admin_view=admin_view) for activity in activities
    ], total


def detail(db: Session, activity_id: str, *, admin_view: bool = False) -> dict:
    activity = get_or_404(db, activity_id)
    # GROUP BY omits activities nobody has rolled on yet.
    stats = stats_for(db, [activity.id]).get(activity.id, RollStats())
    return serialize(activity, stats, admin_view=admin_view)


def _validate_rules(roll_min: int, roll_max: int, settings: Settings) -> None:
    if roll_max < roll_min:
        raise BadRequest("Roll 点最大值必须不小于最小值")
    if roll_min < settings.roll_min_value:
        raise BadRequest(f"Roll 点最小值不能小于 {settings.roll_min_value}")
    if roll_max > settings.roll_max_value:
        raise BadRequest(f"Roll 点最大值不能大于 {settings.roll_max_value}")


def create(
    db: Session, payload: ActivityInput, actor: Principal, ip: str, settings: Settings
) -> dict:
    _validate_rules(payload.roll_min, payload.roll_max, settings)
    now = utc_now()
    activity = Activity(
        id=generate_activity_id(),
        name=payload.name,
        description=payload.description,
        status=ActivityStatus.ACTIVE,
        roll_min=payload.roll_min,
        roll_max=payload.roll_max,
        max_participations=payload.max_participations,
        max_participants=payload.max_participants,
        created_at=now,
        started_at=now,
        created_by_id=actor.admin_id,
    )
    db.add(activity)
    audit.record(
        db,
        action="activity.created",
        actor=actor,
        target_type="activity",
        target_id=activity.id,
        detail={"name": activity.name, "range": [activity.roll_min, activity.roll_max],
                "max_participants": activity.max_participants},
        ip=ip,
    )
    _commit(db)
    stats = RollStats()
    return serialize(activity, stats, admin_view=True)


def update(
    db: Session, activity_id: str, payload: ActivityUpdate, actor: Principal, ip: str, settings: Settings
) -> dict:
    activity = get_or_404(db, activity_id)
    changes: dict[str, Any] = {}

    if payload.name is not None and payload.name != activity.name:
        changes["name"] = {"from": activity.name, "to": payload.name}
        activity.name = payload.name
    if payload.description is not None and payload.description != (activity.description or ""):
        changes["description"] = {"from": activity.description, "to": payload.description}
        activity.description = payload.description

    roll_min = payload.roll_min if payload.roll_min is not None else activity.roll_min
    roll_max = payload.roll_max if payload.roll_max is not None else activity.roll_max
    if (roll_min, roll_max) != (activity.roll_min, activity.roll_max):
        _validate_rules(roll_min, roll_max, settings)
        _assert_range_covers_existing(db, activity, roll_min, roll_max)
        changes["range"] = {"from": [activity.roll_min, activity.roll_max], "to": [roll_min, roll_max]}
        activity.roll_min, activity.roll_max = roll_min, roll_max

    if payload.max_participations is not None and payload.max_participations != activity.max_participations:
        changes["max_participations"] = {
            "from": activity.max_participations,
            "to": payload.max_participations,
        }
        activity.max_participations = payload.max_participations

    if payload.max_participants is not None and payload.max_participants != activity.max_participants:
        changes["max_participants"] = {
            "from": activity.max_participants,
            "to": payload.max_participants,
        }
        activity.max_participants = payload.max_participants

    if changes:
        activity.updated_at = utc_now()
        audit.record(
            db,
            action="activity.updated",
            actor=actor,
            target_type="activity",
            target_id=activity.id,
            detail=changes,
            ip=ip,
        )
        _commit(db)

    return detail(db, activity.id, admin_view=True)


def _assert_range_covers_existing(db: Session, activity: Activity, roll_min: int, roll_max: int) -> None:
    bounds = db.execute(
        select(func.min(RollResult.number), func.max(RollResult.number)).where(
            RollResult.activity_id == activity.id, RollResult.status == RollStatus.VALID
        )
    ).one()
    low, high = bounds
    if low is None:
        return
    if roll_min > low or roll_max < high:
        raise Conflict(f"范围不能收窄，已有有效 Roll 点覆盖 {low}-{high}")


def set_status(
    db: Session, activity_id: str, payload: ActivityStatusUpdate, actor: Principal, ip: str
) -> dict:
    activity = get_or_404(db, activity_id)
    target = payload.status
    current = activity.status
    now = utc_now()

    if current == target:
        return detail(db, activity.id, admin_view=True)
    if current in TERMINAL_STATUSES and target is not ActivityStatus.ACTIVE:
        raise Conflict("活动已结束，只能重新开启")
    if target is ActivityStatus.ACTIVE and _valid_roll_count(db, activity.id) >= activity.range_size:
        raise Conflict("数值已全部 Roll 完，无法重新开启")

    activity.status = target
    activity.updated_at = now
    if target is ActivityStatus.ACTIVE:
        activity.started_at = activity.started_at or now
        activity.ended_at = None
    elif target is ActivityStatus.ENDED:
        activity.ended_at = now

    audit.record(
        db,
        action=f"activity.{target.value}",
        actor=actor,
        target_type="activity",
        target_id=activity.id,
        detail={"from": current.value, "to": target.value},
        ip=ip,
    )
    _commit(db)
    return detail(db, activity.id, admin_view=True)


def remove(db: Session, activity_id: str, actor: Principal, ip: str) -> str:
    activity = get_or_404(db, activity_id)
    name = activity.name
    db.delete(activity)
    audit.record(
        db,
        action="activity.deleted",
        actor=actor,
        target_type="activity",
        target_id=activity_id,
        detail={"name": name},
        ip=ip,
    )
    _commit(db)
    return name


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(f"数据冲突：{exc.orig}") from exc


def _valid_roll_count(db: Session, activity_id: str) -> int:
    return db.execute(
        select(func.count(RollResult.id)).where(
            RollResult.activity_id == activity_id, RollResult.status == RollStatus.VALID
        )
    ).scalar_one()
