"""Public read endpoints and the roll action itself."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import TooManyRequests
from app.core.security import client_ip, roll_limiter
from app.db.models import ActivityStatus
from app.schemas.activity import ActivityPublic
from app.schemas.common import Page
from app.schemas.roll import RollPublic, RollSubmit
from app.services import activity as activity_service
from app.services import roll as roll_service
from app.services import stats as stats_service

router = APIRouter(tags=["activities"])
STATUS_VALUES = {item.value: item for item in ActivityStatus}


@router.get("/activities", response_model=Page[ActivityPublic])
async def list_activities(
    db: DbSession,
    status: str = Query(default="", max_length=8, description="active | paused | ended"),
    q: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = activity_service.list_page(
        db,
        q=q.strip(),
        status=STATUS_VALUES.get(status),
        only_public=True,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/activities/{activity_id}", response_model=ActivityPublic)
async def get_activity(activity_id: str, db: DbSession) -> dict:
    return activity_service.detail(db, activity_id)


@router.get("/activities/{activity_id}/rolls", response_model=list[RollPublic])
async def list_rolls(
    activity_id: str,
    db: DbSession,
    status: str = Query(default="valid", pattern="^(valid|void|all)$"),
    order: str = Query(default="number", pattern="^(number|time|name)$"),
) -> list[dict]:
    activity_service.get_or_404(db, activity_id)
    return roll_service.list_serialized(db, activity_id, status=status, order=order)


@router.get("/activities/{activity_id}/stats")
async def activity_stats(activity_id: str, db: DbSession) -> dict:
    activity = activity_service.get_or_404(db, activity_id)
    return stats_service.activity_stats(db, activity)


@router.post("/activities/{activity_id}/rolls", status_code=201)
async def submit_roll(activity_id: str, body: RollSubmit, request: Request, db: DbSession) -> dict:
    settings = get_settings()
    ip = client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    allowed, retry_after = roll_limiter.check(
        f"roll:{ip}:{activity_id}", settings.roll_rate_limit, settings.roll_rate_window_seconds
    )
    if not allowed:
        raise TooManyRequests(f"操作过于频繁，请 {retry_after} 秒后再试")

    activity = activity_service.get_or_404(db, activity_id)
    roll, rank = roll_service.submit(db, activity, body.name, ip)
    serialized = roll_service.serialize(roll, rank)

    await request.app.state.ws_manager.broadcast(activity_id, {"type": "roll_result", "result": serialized})

    return {
        "roll": serialized,
        "activity": activity_service.detail(db, activity_id),
        "message": f"{body.name} Roll 到 {roll.number}",
    }
