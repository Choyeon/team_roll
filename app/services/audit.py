"""Write-only audit trail for administrative actions."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.time import to_utc, utc_now
from app.db.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor: Principal | None = None,
    actor_label: str = "system",
    target_type: str = "",
    target_id: str = "",
    detail: Any = None,
    ip: str = "",
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_label=actor.username if actor else actor_label,
        actor_id=actor.admin_id if actor else None,
        target_type=target_type,
        target_id=target_id,
        detail=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else "",
        ip=ip,
        created_at=utc_now(),
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def query(
    db: Session,
    *,
    q: str = "",
    action: str = "",
    actor: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(
            AuditLog.action.like(like)
            | AuditLog.actor_label.like(like)
            | AuditLog.target_id.like(like)
            | AuditLog.detail.like(like)
        )
    if action:
        filters.append(AuditLog.action == action)
    if actor:
        filters.append(AuditLog.actor_label == actor)
    if date_from:
        start = datetime.combine(datetime.strptime(date_from, "%Y-%m-%d").date(), time.min)
        filters.append(AuditLog.created_at >= to_utc(start))
    if date_to:
        end = datetime.combine(datetime.strptime(date_to, "%Y-%m-%d").date(), time.max)
        filters.append(AuditLog.created_at <= to_utc(end))

    stmt: Select = select(AuditLog)
    for condition in filters:
        stmt = stmt.where(condition)

    total = db.execute(select(func.count(AuditLog.id)).where(*filters)).scalar_one()
    rows = db.execute(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return list(rows), total


def recent(db: Session, limit: int = 10) -> list[AuditLog]:
    return list(db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).scalars())


def distinct_actions(db: Session) -> list[str]:
    return list(db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action)).scalars())


def purge_older_than(db: Session, days: int) -> int:
    cutoff = utc_now() - timedelta(days=max(1, days))
    deleted = db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff)).rowcount
    db.commit()
    return int(deleted or 0)
