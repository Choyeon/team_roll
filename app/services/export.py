"""CSV / JSON exports and housekeeping."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import timedelta

from sqlalchemy import and_, delete, distinct, func, select
from sqlalchemy.orm import Session, aliased

from app.core.time import utc_now
from app.db.models import Activity, AdminSession, AuditLog, RollResult, RollStatus

BOM = "﻿"
CHUNK_LIMIT = 200


def _start_row_stream(header: list[str]) -> tuple[io.StringIO, csv.writer, str]:
    buffer = io.StringIO()
    buffer.write(BOM)
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    prefix = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return buffer, writer, prefix


def _drain(buffer: io.StringIO) -> str:
    value = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return value


def _valid_ranks(db: Session, activity_ids: set[str]) -> dict[str, int]:
    """rank = 1 + how many valid numbers are strictly greater, computed per activity."""
    if not activity_ids:
        return {}
    current, higher = aliased(RollResult), aliased(RollResult)
    rows = db.execute(
        select(current.id, func.count(higher.number))
        .outerjoin(
            higher,
            and_(
                higher.activity_id == current.activity_id,
                higher.number > current.number,
                higher.status == RollStatus.VALID,
            ),
        )
        .where(current.activity_id.in_(activity_ids), current.status == RollStatus.VALID)
        .group_by(current.id)
    ).all()
    return {roll_id: int(count or 0) + 1 for roll_id, count in rows}


def rolls_csv(db: Session, *, activity_id: str | None = None, status: str = "all") -> Iterator[str]:
    buffer, writer, prefix = _start_row_stream(
        ["result_id", "activity_id", "activity_name", "name", "number", "status", "rank", "ip", "rolled_at_utc"]
    )
    yield prefix

    stmt = (
        select(RollResult, Activity.name)
        .join(Activity, Activity.id == RollResult.activity_id)
        .order_by(Activity.created_at.desc(), RollResult.number.desc())
    )
    if activity_id:
        stmt = stmt.where(RollResult.activity_id == activity_id)
    if status in {"valid", "void"}:
        stmt = stmt.where(RollResult.status == RollStatus(status))

    rows = db.execute(stmt).all()
    ranks = _valid_ranks(db, {roll.activity_id for roll, _ in rows})
    for roll, activity_name in rows:
        writer.writerow(
            [
                roll.id,
                roll.activity_id,
                activity_name,
                roll.name,
                roll.number,
                roll.status.value,
                ranks.get(roll.id, "") if roll.status is RollStatus.VALID else "",
                roll.ip or "",
                roll.timestamp.isoformat(),
            ]
        )
        yield _drain(buffer)


def activities_csv(db: Session) -> Iterator[str]:
    buffer, writer, prefix = _start_row_stream(
        [
            "id", "name", "description", "status", "roll_min", "roll_max", "max_participations",
            "valid_rolls", "void_rolls", "participants", "created_at_utc", "started_at_utc", "ended_at_utc",
        ]
    )
    yield prefix

    rows = db.execute(
        select(
            Activity,
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VALID),
            func.count(RollResult.id).filter(RollResult.status == RollStatus.VOID),
            func.count(distinct(RollResult.name)).filter(RollResult.status == RollStatus.VALID),
        )
        .outerjoin(RollResult, RollResult.activity_id == Activity.id)
        .group_by(Activity.id)
        .order_by(Activity.created_at.desc())
    ).all()

    for activity, valid, void, people in rows:
        writer.writerow(
            [
                activity.id,
                activity.name,
                (activity.description or "").replace("\n", " "),
                activity.status.value,
                activity.roll_min,
                activity.roll_max,
                activity.max_participations,
                int(valid or 0),
                int(void or 0),
                int(people or 0),
                activity.created_at.isoformat(),
                activity.started_at.isoformat() if activity.started_at else "",
                activity.ended_at.isoformat() if activity.ended_at else "",
            ]
        )
        yield _drain(buffer)


def audit_csv(db: Session, *, limit: int = CHUNK_LIMIT * 50) -> Iterator[str]:
    buffer, writer, prefix = _start_row_stream(
        ["id", "created_at_utc", "action", "actor", "target_type", "target_id", "ip", "detail"]
    )
    yield prefix
    rows = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars().all()
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat(),
                row.action,
                row.actor_label,
                row.target_type,
                row.target_id,
                row.ip,
                row.detail,
            ]
        )
        yield _drain(buffer)


def snapshot_json(db: Session) -> str:
    activities = db.execute(select(Activity).order_by(Activity.created_at.desc())).scalars().all()
    payload = {
        "generated_at": utc_now().isoformat(),
        "activities": [
            {
                "id": activity.id,
                "name": activity.name,
                "description": activity.description,
                "status": activity.status.value,
                "roll_min": activity.roll_min,
                "roll_max": activity.roll_max,
                "max_participations": activity.max_participations,
                "created_at": activity.created_at.isoformat(),
                "rolls": [
                    {
                        "id": roll.id,
                        "name": roll.name,
                        "number": roll.number,
                        "status": roll.status.value,
                        "timestamp": roll.timestamp.isoformat(),
                    }
                    for roll in db.execute(
                        select(RollResult)
                        .where(RollResult.activity_id == activity.id)
                        .order_by(RollResult.number.desc())
                    ).scalars()
                ],
            }
            for activity in activities
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def cleanup(db: Session, *, session_grace_days: int = 1, audit_retention_days: int = 0) -> dict:
    """Drop dead sessions and, when configured, age out audit rows."""
    now = utc_now()
    session_cutoff = now - timedelta(days=max(0, session_grace_days))
    sessions = db.execute(
        delete(AdminSession).where(
            (AdminSession.revoked_at.is_not(None) & (AdminSession.revoked_at < session_cutoff))
            | (AdminSession.expires_at < session_cutoff)
        )
    ).rowcount

    audit_deleted = 0
    if audit_retention_days > 0:
        audit_cutoff = now - timedelta(days=audit_retention_days)
        audit_deleted = db.execute(delete(AuditLog).where(AuditLog.created_at < audit_cutoff)).rowcount

    db.commit()
    return {"sessions_removed": int(sessions or 0), "audit_removed": int(audit_deleted or 0)}
