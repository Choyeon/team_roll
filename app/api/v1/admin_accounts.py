"""Admin accounts and login sessions."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.deps import CsrfProtected, DbSession, Manager, Superuser, load_active_session
from app.schemas.auth import AdminCreate, AdminOut, AdminUpdate, SessionOut
from app.services import admins as admin_service
from app.services import auth as auth_service

router = APIRouter(prefix="/admin", tags=["admin-accounts"], dependencies=[CsrfProtected])


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(_actor: Manager, request: Request, db: DbSession) -> list[dict]:
    settings = get_settings()
    current, _ = load_active_session(request, db, settings)
    return auth_service.list_sessions(db, include_revoked=False, current_id=current.id)


@router.delete("/sessions/{session_id}")
async def revoke_session(actor: Manager, request: Request, session_id: str, db: DbSession) -> dict:
    session = auth_service.revoke(db, session_id, actor=actor, ip=request.state.client_ip)
    return {"message": f"已强制 {session.username} 的会话下线"}


@router.delete("/sessions")
async def revoke_own_sessions(actor: Manager, request: Request, db: DbSession) -> dict:
    settings = get_settings()
    current, _ = load_active_session(request, db, settings)
    count = auth_service.revoke_all_for(
        db, actor.admin_id, actor=actor, ip=request.state.client_ip, keep=current.id
    )
    return {"message": f"已下线该账户其他 {count} 个会话"}


@router.get("/admins", response_model=list[AdminOut])
async def list_admins(_: Superuser, db: DbSession) -> list[dict]:
    return admin_service.list_all(db)


@router.post("/admins", response_model=AdminOut, status_code=201)
async def create_admin(payload: AdminCreate, actor: Superuser, request: Request, db: DbSession) -> dict:
    return admin_service.create(db, payload, actor, request.state.client_ip)


@router.patch("/admins/{admin_id}", response_model=AdminOut)
async def update_admin(
    admin_id: int, payload: AdminUpdate, actor: Superuser, request: Request, db: DbSession
) -> dict:
    return admin_service.update(db, admin_id, payload, actor, request.state.client_ip)


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, actor: Superuser, request: Request, db: DbSession) -> dict:
    username = admin_service.remove(db, admin_id, actor, request.state.client_ip)
    return {"message": f"管理员 {username} 已删除"}
