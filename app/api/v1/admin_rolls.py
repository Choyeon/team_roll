"""Admin roll-table management."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core.deps import CsrfProtected, DbSession, Manager
from app.db.models import RollStatus
from app.schemas.roll import RollAdminOut, RollManualCreate, RollUpdate, RollVoid
from app.services import activity as activity_service
from app.services import roll as roll_service
from app.services import stats as stats_service

router = APIRouter(prefix="/admin", tags=["admin-rolls"], dependencies=[CsrfProtected])


@router.get("/activities/{activity_id}/rolls")
async def list_activity_rolls(
    _: Manager,
    activity_id: str,
    db: DbSession,
    status: str = Query(default="all", pattern="^(valid|void|all)$"),
    order: str = Query(default="number", pattern="^(number|time|name)$"),
) -> dict:
    activity = activity_service.get_or_404(db, activity_id)
    stats = activity_service.stats_for(db, [activity_id])[activity_id]
    return {
        "activity": activity_service.serialize(activity, stats, admin_view=True),
        "stats": stats_service.activity_stats(db, activity),
        "rolls": roll_service.list_serialized(db, activity_id, status=status, order=order, admin_view=True),
    }


@router.post("/activities/{activity_id}/rolls", response_model=RollAdminOut, status_code=201)
async def add_roll_manually(
    payload: RollManualCreate, actor: Manager, request: Request, activity_id: str, db: DbSession
) -> dict:
    result = roll_service.create_manually(db, activity_id, payload, actor, request.state.client_ip)
    await request.app.state.ws_manager.broadcast(activity_id, {"type": "roll_result", "result": result})
    return result


@router.patch("/rolls/{roll_id}", response_model=RollAdminOut)
async def modify_roll(payload: RollUpdate, actor: Manager, request: Request, roll_id: str, db: DbSession) -> dict:
    result = roll_service.modify(db, roll_id, payload, actor, request.state.client_ip)
    await request.app.state.ws_manager.broadcast(result["activity_id"], {"type": "roll_updated", "result": result})
    return result


@router.put("/rolls/{roll_id}/void", response_model=RollAdminOut)
async def void_roll(payload: RollVoid, actor: Manager, request: Request, roll_id: str, db: DbSession) -> dict:
    result = roll_service.set_status(
        db, roll_id, status=RollStatus.VOID, reason=payload.reason, actor=actor, ip=request.state.client_ip
    )
    await request.app.state.ws_manager.broadcast(result["activity_id"], {"type": "roll_updated", "result": result})
    return result


@router.put("/rolls/{roll_id}/restore", response_model=RollAdminOut)
async def restore_roll(actor: Manager, request: Request, roll_id: str, db: DbSession) -> dict:
    result = roll_service.set_status(db, roll_id, status=RollStatus.VALID, reason="", actor=actor,
                                     ip=request.state.client_ip)
    await request.app.state.ws_manager.broadcast(result["activity_id"], {"type": "roll_updated", "result": result})
    return result


@router.delete("/rolls/{roll_id}")
async def delete_roll(actor: Manager, request: Request, roll_id: str, db: DbSession) -> dict:
    snapshot = roll_service.delete(db, roll_id, actor=actor, ip=request.state.client_ip)
    await request.app.state.ws_manager.broadcast(
        snapshot["activity_id"], {"type": "roll_deleted", "result_id": snapshot["id"]}
    )
    return {"message": f"已删除 {snapshot['name']} 的 Roll 记录（数值 {snapshot['number']} 已释放）"}
