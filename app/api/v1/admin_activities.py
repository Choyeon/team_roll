"""Admin activity management: listing, creation, rules editing, status, deletion."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.config import get_settings
from app.core.deps import CsrfProtected, Dangerous, DbSession, Manager, Reader
from app.db.models import ActivityStatus
from app.schemas.activity import ActivityAdminOut, ActivityInput, ActivityStatusUpdate, ActivityUpdate
from app.schemas.common import Page
from app.services import activity as activity_service
from app.services import stats as stats_service

router = APIRouter(prefix="/admin/activities", tags=["admin-activities"], dependencies=[CsrfProtected])
STATUS_VALUES = {item.value: item for item in ActivityStatus}


def _paged(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "meta": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
    }


@router.get("", response_model=Page[ActivityAdminOut])
async def list_activities(
    _: Reader,
    db: DbSession,
    status: str = Query(default="", max_length=8),
    q: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    items, total = activity_service.list_page(
        db, q=q.strip(), status=STATUS_VALUES.get(status), page=page, page_size=page_size, admin_view=True
    )
    return _paged(items, total, page, page_size)


@router.post("", response_model=ActivityAdminOut, status_code=201)
async def create_activity(payload: ActivityInput, actor: Manager, request: Request, db: DbSession) -> dict:
    return activity_service.create(db, payload, actor, request.state.client_ip, get_settings())


@router.get("/{activity_id}", response_model=ActivityAdminOut)
async def get_activity(_: Reader, activity_id: str, db: DbSession) -> dict:
    return activity_service.detail(db, activity_id, admin_view=True)


@router.patch("/{activity_id}", response_model=ActivityAdminOut)
async def update_activity(
    payload: ActivityUpdate, actor: Manager, request: Request, activity_id: str, db: DbSession
) -> dict:
    result = activity_service.update(db, activity_id, payload, actor, request.state.client_ip, get_settings())
    await request.app.state.ws_manager.broadcast(
        activity_id, {"type": "activity_updated", "activity": result}
    )
    return result


@router.put("/{activity_id}/status", response_model=ActivityAdminOut)
async def set_activity_status(
    payload: ActivityStatusUpdate, actor: Manager, request: Request, activity_id: str, db: DbSession
) -> dict:
    result = activity_service.set_status(db, activity_id, payload, actor, request.state.client_ip)
    await request.app.state.ws_manager.broadcast(
        activity_id, {"type": "activity_status", "status": result["status"], "activity": result}
    )
    return result


@router.delete("/{activity_id}")
async def delete_activity(actor: Dangerous, request: Request, activity_id: str, db: DbSession) -> dict:
    name = activity_service.remove(db, activity_id, actor, request.state.client_ip)
    await request.app.state.ws_manager.broadcast(
        activity_id, {"type": "activity_deleted", "activity_id": activity_id}
    )
    return {"message": f"活动「{name}」及其 Roll 记录已删除"}


@router.get("/{activity_id}/stats")
async def activity_statistics(_: Reader, activity_id: str, db: DbSession) -> dict:
    activity = activity_service.get_or_404(db, activity_id)
    return stats_service.activity_stats(db, activity)
