"""Administrator authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.core.config import get_settings
from app.core.deps import CsrfProtected, DbSession, Principal, RequesterIp, capabilities_for, load_active_session
from app.core.errors import AppError
from app.core.security import client_ip
from app.schemas.auth import LoginRequest, MeOut, PasswordChange
from app.services import audit, auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(
        key=settings.cookie_name,
        value=session_id,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    # Deliberately JS-readable: it is a double-submit token, not a credential.
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _principal(admin, session_id: str) -> Principal:
    return Principal(
        admin_id=admin.id,
        username=admin.username,
        display_name=admin.display_name or admin.username,
        role=admin.role,
        session_id=session_id,
    )


def _me_out(admin, session) -> MeOut:
    return MeOut(
        username=admin.username,
        display_name=admin.display_name or admin.username,
        role=admin.role,
        capabilities=capabilities_for(admin.role),
        csrf_token=session.csrf_token,
        expires_at=session.expires_at,
        last_login_at=admin.last_login_at,
    )


@router.post("/login", response_model=MeOut)
async def login(payload: LoginRequest, request: Request, db: DbSession, response: Response) -> MeOut:
    settings = get_settings()
    session, admin = auth.authenticate(
        db,
        username=payload.username.strip(),
        password=payload.password,
        ip=client_ip(request, trust_proxy_headers=settings.trust_proxy_headers),
        user_agent=request.headers.get("user-agent", ""),
        settings=settings,
    )
    _set_session_cookie(response, session.id, session.csrf_token)
    return _me_out(admin, session)


@router.post("/logout")
async def logout(request: Request, db: DbSession, response: Response) -> dict:
    settings = get_settings()
    try:
        session, admin = load_active_session(request, db, settings)
    except AppError:
        _clear_session_cookie(response)
        return {"message": "已登出"}
    auth.close_session(
        db,
        session,
        actor=_principal(admin, session.id),
        ip=client_ip(request, trust_proxy_headers=settings.trust_proxy_headers),
    )
    _clear_session_cookie(response)
    return {"message": "已登出"}


@router.get("/me", response_model=MeOut)
async def me(request: Request, db: DbSession) -> MeOut:
    session, admin = load_active_session(request, db, get_settings())
    return _me_out(admin, session)


@router.post("/password", dependencies=[CsrfProtected], status_code=status.HTTP_200_OK)
async def change_password(
    payload: PasswordChange, request: Request, db: DbSession, response: Response, ip: RequesterIp
) -> dict:
    settings = get_settings()
    _, admin = load_active_session(request, db, settings)
    session = auth.change_own_password(
        db, admin, current=payload.current_password, new=payload.new_password, settings=settings
    )
    audit.record(
        db,
        action="admin.password_changed",
        actor=_principal(admin, session.id),
        target_type="admin",
        target_id=admin.username,
        ip=ip,
        commit=True,
    )
    _set_session_cookie(response, session.id, session.csrf_token)
    return {"message": "密码已更新，其他会话已失效"}
