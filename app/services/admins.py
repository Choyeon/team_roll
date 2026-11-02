"""Administrator account management (super-role only operations)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import CAPABILITIES, Principal
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.security import hash_password
from app.core.time import utc_now
from app.db.models import Admin, AdminRole
from app.schemas.auth import AdminCreate, AdminUpdate
from app.services import audit, auth

SUPER_ROLES = {AdminRole.SUPER}


def serialize(admin: Admin) -> dict:
    return {
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name or admin.username,
        "role": admin.role,
        "is_active": admin.is_active,
        "created_at": admin.created_at,
        "last_login_at": admin.last_login_at,
        "last_login_ip": admin.last_login_ip or "",
        "failed_login_count": admin.failed_login_count,
        "locked_until": admin.locked_until,
        "capabilities": sorted(CAPABILITIES.get(admin.role, set())),
    }


def get_or_404(db: Session, admin_id: int) -> Admin:
    admin = db.get(Admin, admin_id)
    if admin is None:
        raise NotFound("管理员账户不存在")
    return admin


def list_all(db: Session) -> list[dict]:
    rows = db.execute(select(Admin).order_by(Admin.username)).scalars().all()
    return [serialize(admin) for admin in rows]


def create(db: Session, payload: AdminCreate, actor: Principal, ip: str) -> dict:
    exists = db.execute(select(func.count(Admin.id)).where(Admin.username == payload.username)).scalar_one()
    if exists:
        raise Conflict("该用户名已存在")
    admin = Admin(
        username=payload.username,
        display_name=payload.display_name or payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(admin)
    audit.record(
        db,
        action="admin.created",
        actor=actor,
        target_type="admin",
        target_id=payload.username,
        detail={"role": payload.role.value},
        ip=ip,
    )
    auth.commit_unique_username(db)
    db.refresh(admin)
    return serialize(admin)


def update(db: Session, admin_id: int, payload: AdminUpdate, actor: Principal, ip: str) -> dict:
    admin = get_or_404(db, admin_id)
    changes: dict = {}

    if payload.password:
        if len(payload.password) < 10:
            raise BadRequest("密码长度至少 10 位")
        admin.password_hash = hash_password(payload.password)
        changes["password"] = "reset"
        admin.failed_login_count = 0
        admin.locked_until = None
    if payload.display_name is not None and payload.display_name != admin.display_name:
        changes["display_name"] = {"from": admin.display_name, "to": payload.display_name}
        admin.display_name = payload.display_name
    if payload.role is not None and payload.role != admin.role:
        _guard_role_change(db, admin, payload.role)
        changes["role"] = {"from": admin.role.value, "to": payload.role.value}
        admin.role = payload.role
    if payload.is_active is not None and payload.is_active != admin.is_active:
        if not payload.is_active:
            _guard_deactivation(db, admin, actor)
        changes["is_active"] = {"from": admin.is_active, "to": payload.is_active}
        admin.is_active = payload.is_active

    if changes:
        admin.updated_at = utc_now()
        audit.record(
            db,
            action="admin.updated",
            actor=actor,
            target_type="admin",
            target_id=admin.username,
            detail=changes,
            ip=ip,
        )
        if {"password", "is_active", "role"} & set(changes):
            auth.revoke_all_for(db, admin.id, actor=actor, ip=ip)
        db.commit()

    return serialize(admin)


def remove(db: Session, admin_id: int, actor: Principal, ip: str) -> str:
    admin = get_or_404(db, admin_id)
    if admin.id == actor.admin_id:
        raise BadRequest("不能删除当前登录的账户")
    _guard_last_super(db, admin)
    username = admin.username
    db.delete(admin)
    audit.record(db, action="admin.deleted", actor=actor, target_type="admin", target_id=username, ip=ip)
    db.commit()
    return username


def _guard_role_change(db: Session, admin: Admin, new_role: AdminRole) -> None:
    if admin.role in SUPER_ROLES and new_role not in SUPER_ROLES:
        _guard_last_super(db, admin)


def _guard_deactivation(db: Session, admin: Admin, actor: Principal) -> None:
    if admin.id == actor.admin_id:
        raise BadRequest("不能停用当前登录的账户")
    _guard_last_super(db, admin)


def _guard_last_super(db: Session, admin: Admin) -> None:
    if admin.role not in SUPER_ROLES or not admin.is_active:
        return
    remaining = db.execute(
        select(func.count(Admin.id)).where(
            Admin.role == AdminRole.SUPER, Admin.is_active.is_(True), Admin.id != admin.id
        )
    ).scalar_one()
    if remaining == 0:
        raise Conflict("必须保留至少一个可用的超级管理员")


def bootstrap_admin(db: Session, settings: Settings) -> Admin | None:
    """Create the first administrator from env config when the table is empty."""
    if db.execute(select(func.count(Admin.id))).scalar_one() > 0:
        return None
    if settings.bootstrap_admin_password is None:
        return None
    admin = Admin(
        username=settings.bootstrap_admin_username,
        display_name=settings.bootstrap_admin_username,
        password_hash=hash_password(settings.bootstrap_admin_password.get_secret_value()),
        role=AdminRole.SUPER,
        is_active=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(admin)
    db.commit()
    audit.record(
        db,
        action="admin.bootstrapped",
        actor_label="system",
        target_type="admin",
        target_id=admin.username,
        detail={"role": AdminRole.SUPER.value, "source": "environment"},
        commit=True,
    )
    return admin
