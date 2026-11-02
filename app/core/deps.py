"""Shared FastAPI dependencies: database, authenticated principal, CSRF, RBAC."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.security import client_ip
from app.core.time import utc_now
from app.db.models import Admin, AdminRole, AdminSession
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

SESSION_TOUCH_SECONDS = 60

CAPABILITIES: dict[AdminRole, set[str]] = {
    AdminRole.SUPER: {"read", "manage", "manage_admins", "dangerous"},
    AdminRole.ADMIN: {"read", "manage", "dangerous"},
    AdminRole.VIEWER: {"read"},
}


@dataclass(frozen=True)
class Principal:
    admin_id: int
    username: str
    display_name: str
    role: AdminRole
    session_id: str

    def can(self, capability: str) -> bool:
        return capability in CAPABILITIES.get(self.role, set())


def capabilities_for(role: AdminRole) -> list[str]:
    return sorted(CAPABILITIES.get(role, set()))


def load_active_session(request: Request, db: Session, settings: Settings) -> tuple[AdminSession, Admin]:
    session_id = request.cookies.get(settings.cookie_name)
    if not session_id:
        raise Unauthorized("请先登录管理员账户")

    session = db.get(AdminSession, session_id)
    if session is None or session.revoked_at is not None:
        raise Unauthorized("会话无效，请重新登录")
    if session.is_expired:
        _drop_session(db, session)
        raise Unauthorized("会话已过期，请重新登录")

    admin = db.get(Admin, session.admin_id) if session.admin_id else None
    if admin is None or not admin.is_active:
        _drop_session(db, session)
        raise Unauthorized("账户不存在或已被停用")

    if admin.locked_until and admin.locked_until > utc_now():
        _drop_session(db, session)
        raise Forbidden("账户已被临时锁定")

    now = utc_now()
    if (now - session.last_seen_at).total_seconds() >= SESSION_TOUCH_SECONDS:
        session.last_seen_at = now
        session.expires_at = now + settings.session_ttl
        db.commit()

    return session, admin


def _drop_session(db: Session, session: AdminSession) -> None:
    session.revoked_at = utc_now()
    db.commit()


def require_capability(capability: str):
    """Build a dependency that authenticates the caller and asserts ``capability``."""

    def _dependency(
        request: Request,
        db: DbSession,
        settings: SettingsDep,
    ) -> Principal:
        session, admin = load_active_session(request, db, settings)
        principal = Principal(
            admin_id=admin.id,
            username=admin.username,
            display_name=admin.display_name or admin.username,
            role=admin.role,
            session_id=session.id,
        )
        if not principal.can(capability):
            raise Forbidden("当前角色没有执行该操作的权限")
        return principal

    return _dependency


require_read = require_capability("read")
require_manage = require_capability("manage")
require_super = require_capability("manage_admins")
require_dangerous = require_capability("dangerous")


def verify_csrf(request: Request, db: DbSession, settings: SettingsDep) -> None:
    """Double-submit check for state-changing API calls made with cookie auth."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    session_id = request.cookies.get(settings.cookie_name)
    if not session_id:
        raise Unauthorized("缺少会话，无法校验 CSRF")
    session = db.get(AdminSession, session_id)
    if session is None or not session.csrf_token:
        raise Unauthorized("会话无效，请重新登录")
    supplied = request.headers.get("x-csrf-token")
    if not supplied or not hmac.compare_digest(supplied, session.csrf_token):
        raise Forbidden("CSRF 校验失败，请刷新页面后重试")


def get_client_ip(request: Request, settings: SettingsDep) -> str:
    return client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)


Reader = Annotated[Principal, Depends(require_read)]
Manager = Annotated[Principal, Depends(require_manage)]
Superuser = Annotated[Principal, Depends(require_super)]
Dangerous = Annotated[Principal, Depends(require_dangerous)]
# Router-level dependency: must be a plain Depends() object, not an Annotated alias.
CsrfProtected = Depends(verify_csrf)
RequesterIp = Annotated[str, Depends(get_client_ip)]
