"""Roll point engine: number allocation, ranking, and administrative corrections.

Invariants enforced here:
  * a number may be held by at most one *valid* result per activity,
  * ``max_participations`` caps how many valid results one name may hold,
  * ``max_participants`` caps how many distinct names may join (0 = unlimited),
  * voiding a result releases its number so it can be rolled again.
"""

from __future__ import annotations

import secrets
import threading
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.security import generate_token
from app.core.time import utc_now
from app.db.models import Activity, ActivityStatus, RollResult, RollStatus
from app.schemas.roll import RollManualCreate, RollUpdate
from app.services import audit

NUMBER_RETRIES = 4
ORDER_FIELDS = {"number": RollResult.number, "time": RollResult.timestamp, "name": RollResult.name}

_submit_locks: dict[str, threading.Lock] = {}
_submit_locks_guard = threading.Lock()


def _submit_lock(activity_id: str) -> threading.Lock:
    with _submit_locks_guard:
        return _submit_locks.setdefault(activity_id, threading.Lock())


def pick_free_number(roll_min: int, roll_max: int, used: set[int]) -> int | None:
    """Uniform pick over the free numbers without materialising the whole range."""
    inside = sorted(value for value in used if roll_min <= value <= roll_max)
    free_total = roll_max - roll_min + 1 - len(inside)
    if free_total <= 0:
        return None
    target = secrets.randbelow(free_total)
    previous = roll_min - 1
    for value in [*inside, roll_max + 1]:
        gap = value - previous - 1
        if target < gap:
            return previous + 1 + target
        target -= gap
        previous = value
    return None


def get_roll_or_404(db: Session, roll_id: str) -> RollResult:
    roll = db.get(RollResult, roll_id)
    if roll is None:
        raise NotFound("Roll 点记录不存在")
    return roll


def activity_rolls(
    db: Session, activity_id: str, *, status: RollStatus | None = RollStatus.VALID, order: str = "number"
) -> list[RollResult]:
    column = ORDER_FIELDS.get(order, RollResult.number)
    stmt = select(RollResult).where(RollResult.activity_id == activity_id)
    if status is not None:
        stmt = stmt.where(RollResult.status == status)
    descending = order in {"number", "time"}
    stmt = stmt.order_by(column.desc() if descending else column.asc())
    return list(db.execute(stmt).scalars().all())


def rank_of(roll: RollResult, ordered_valid: list[RollResult]) -> int:
    for index, candidate in enumerate(ordered_valid, start=1):
        if candidate.id == roll.id:
            return index
    return 0


def serialize(roll: RollResult, rank: int, *, admin_view: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": roll.id,
        "activity_id": roll.activity_id,
        "name": roll.name,
        "number": roll.number,
        "rank": rank,
        "status": roll.status,
        "timestamp": roll.timestamp,
    }
    if admin_view:
        payload["ip"] = roll.ip or ""
        payload["void_reason"] = roll.void_reason or ""
        payload["created_by"] = roll.created_by.username if roll.created_by else ""
    return payload


def list_serialized(
    db: Session, activity_id: str, *, status: str = "valid", order: str = "number", admin_view: bool = False
) -> list[dict]:
    if status not in {"valid", "void", "all"}:
        raise BadRequest("status 仅支持 valid / void / all")
    wanted = None if status == "all" else RollStatus(status)
    rolls = activity_rolls(db, activity_id, status=wanted, order=order)
    if wanted is RollStatus.VOID:
        return [serialize(roll, 0, admin_view=admin_view) for roll in rolls]
    ranking = activity_rolls(db, activity_id, status=RollStatus.VALID, order="number")
    return [serialize(roll, rank_of(roll, ranking), admin_view=admin_view) for roll in rolls]


def _assert_rollable(activity: Activity) -> None:
    if activity.status is ActivityStatus.ENDED:
        raise Conflict("活动已结束，无法继续参与 Roll 点")
    if activity.status is ActivityStatus.PAUSED:
        raise Conflict("活动已暂停，稍后再试")


def _assert_participation_quota(db: Session, activity: Activity, name: str) -> None:
    held = db.execute(
        select(func.count(RollResult.id)).where(
            RollResult.activity_id == activity.id,
            RollResult.name == name,
            RollResult.status == RollStatus.VALID,
        )
    ).scalar_one()
    if held >= activity.max_participations:
        if activity.max_participations == 1:
            raise Conflict("你已经参与过了")
        raise Conflict(f"每人最多参与 {activity.max_participations} 次，你已参与 {held} 次")


def _participant_names(db: Session, activity_id: str) -> set[str]:
    rows = db.execute(
        select(distinct(RollResult.name)).where(
            RollResult.activity_id == activity_id, RollResult.status == RollStatus.VALID
        )
    ).scalars()
    return set(rows)


def _assert_participant_slots(db: Session, activity: Activity, name: str) -> None:
    """A capped activity stays open to the people already on the board."""
    if activity.max_participants <= 0:
        return
    joined = _participant_names(db, activity.id)
    if name in joined:
        return
    if len(joined) >= activity.max_participants:
        raise Conflict(f"本次活动仅限 {activity.max_participants} 人参与，名额已满")


def submit(db: Session, activity: Activity, name: str, ip: str) -> tuple[RollResult, int]:
    """Serialise submits per activity.

    Number uniqueness has a partial unique index to fall back on; the
    participant cap is a count over other people's rows, so two teammates
    clicking at the same instant could otherwise both pass the check and take
    the last slot. The deployment is single-worker, so a process lock is enough.
    """
    with _submit_lock(activity.id):
        return _submit(db, activity, name, ip)


def _submit(db: Session, activity: Activity, name: str, ip: str) -> tuple[RollResult, int]:
    """Allocate a fresh number for ``name``; retried on concurrent number collisions."""
    _assert_rollable(activity)
    _assert_participation_quota(db, activity, name)
    _assert_participant_slots(db, activity, name)

    used = {roll.number for roll in activity_rolls(db, activity.id, status=RollStatus.VALID, order="number")}
    for _ in range(NUMBER_RETRIES):
        number = pick_free_number(activity.roll_min, activity.roll_max, used)
        if number is None:
            raise Conflict("所有数值已经被 Roll 完，无法继续参与")
        roll = RollResult(
            id=generate_token(24),
            activity_id=activity.id,
            name=name,
            number=number,
            ip=ip,
            status=RollStatus.VALID,
            timestamp=utc_now(),
        )
        db.add(roll)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Another participant took this number first: exclude it and draw again.
            used.add(number)
            _assert_participation_quota(db, activity, name)
            _assert_participant_slots(db, activity, name)
            continue
        db.refresh(roll)
        ranking = activity_rolls(db, activity.id, status=RollStatus.VALID, order="number")
        return roll, rank_of(roll, ranking)

    raise Conflict("Roll 点过于频繁，请稍后重试")


def create_manually(
    db: Session, activity_id: str, payload: RollManualCreate, actor: Principal, ip: str
) -> dict:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise NotFound("活动不存在或已被删除")
    if not activity.roll_min <= payload.number <= activity.roll_max:
        raise BadRequest(f"数值需在 {activity.roll_min}-{activity.roll_max} 之间")
    clash = db.execute(
        select(RollResult).where(
            RollResult.activity_id == activity_id,
            RollResult.number == payload.number,
            RollResult.status == RollStatus.VALID,
        )
    ).scalars().first()
    if clash is not None:
        raise Conflict(f"数值 {payload.number} 已被 {clash.name} 持有")

    roll = RollResult(
        id=generate_token(24),
        activity_id=activity_id,
        name=" ".join(payload.name.split()),
        number=payload.number,
        ip=ip,
        status=RollStatus.VALID,
        timestamp=utc_now(),
        created_by_id=actor.admin_id,
    )
    db.add(roll)
    audit.record(
        db,
        action="roll.manual_created",
        actor=actor,
        target_type="roll",
        target_id=roll.id,
        detail={"activity_id": activity_id, "name": roll.name, "number": roll.number, "reason": payload.reason},
        ip=ip,
    )
    db.commit()
    db.refresh(roll)
    ranking = activity_rolls(db, activity_id, status=RollStatus.VALID, order="number")
    return serialize(roll, rank_of(roll, ranking), admin_view=True)


def modify(db: Session, roll_id: str, payload: RollUpdate, actor: Principal, ip: str) -> dict:
    roll = get_roll_or_404(db, roll_id)
    activity = db.get(Activity, roll.activity_id)
    if activity is None:
        raise NotFound("活动不存在或已被删除")

    new_name = " ".join(payload.name.split()) if payload.name else roll.name
    new_number = payload.number if payload.number is not None else roll.number
    if not activity.roll_min <= new_number <= activity.roll_max:
        raise BadRequest(f"数值需在 {activity.roll_min}-{activity.roll_max} 之间")

    clash = db.execute(
        select(RollResult).where(
            RollResult.activity_id == activity.id,
            RollResult.number == new_number,
            RollResult.status == RollStatus.VALID,
            RollResult.id != roll.id,
        )
    ).scalars().first()
    if clash is not None:
        raise Conflict(f"数值 {new_number} 已被 {clash.name} 持有")

    if roll.status is RollStatus.VOID:
        raise Conflict("作废记录不能修改，请先恢复")

    changes = {}
    if new_name != roll.name:
        changes["name"] = {"from": roll.name, "to": new_name}
    if new_number != roll.number:
        changes["number"] = {"from": roll.number, "to": new_number}
    if not changes:
        return serialize(roll, rank_of(roll, activity_rolls(db, activity.id)), admin_view=True)

    roll.name, roll.number = new_name, new_number
    audit.record(
        db,
        action="roll.updated",
        actor=actor,
        target_type="roll",
        target_id=roll.id,
        detail={"activity_id": activity.id, "changes": changes, "reason": payload.reason},
        ip=ip,
    )
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise Conflict("数值已被占用，请刷新后重试") from err
    db.refresh(roll)
    ranking = activity_rolls(db, activity.id, status=RollStatus.VALID, order="number")
    return serialize(roll, rank_of(roll, ranking), admin_view=True)


def set_status(
    db: Session, roll_id: str, *, status: RollStatus, reason: str, actor: Principal, ip: str
) -> dict:
    roll = get_roll_or_404(db, roll_id)
    activity_id = roll.activity_id
    if roll.status is status:
        return serialize(roll, rank_of(roll, activity_rolls(db, activity_id)), admin_view=True)

    if status is RollStatus.VALID:
        holder = db.execute(
            select(RollResult).where(
                RollResult.activity_id == activity_id,
                RollResult.number == roll.number,
                RollResult.status == RollStatus.VALID,
                RollResult.id != roll.id,
            )
        ).scalars().first()
        if holder is not None:
            raise Conflict(f"数值 {roll.number} 已被 {holder.name} 持有，无法恢复")
        roll.void_reason = ""
        roll.voided_at = None
    else:
        roll.void_reason = reason
        roll.voided_at = utc_now()

    roll.status = status
    audit.record(
        db,
        action=f"roll.{status.value}",
        actor=actor,
        target_type="roll",
        target_id=roll.id,
        detail={"activity_id": activity_id, "name": roll.name, "number": roll.number, "reason": reason},
        ip=ip,
    )
    db.commit()
    db.refresh(roll)
    ranking = activity_rolls(db, activity_id, status=RollStatus.VALID, order="number")
    return serialize(roll, rank_of(roll, ranking), admin_view=True)


def delete(db: Session, roll_id: str, *, actor: Principal, ip: str) -> dict:
    roll = get_roll_or_404(db, roll_id)
    snapshot = serialize(roll, 0, admin_view=True)
    activity_id = roll.activity_id
    db.delete(roll)
    audit.record(
        db,
        action="roll.deleted",
        actor=actor,
        target_type="roll",
        target_id=roll_id,
        detail=snapshot,
        ip=ip,
    )
    db.commit()
    snapshot["activity_id"] = activity_id
    return snapshot
