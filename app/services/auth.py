"""Authentication and admin session lifecycle."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import Conflict, Forbidden, NotFound, TooManyRequests, Unauthorized
from app.core.security import generate_token, hash_password, login_limiter, verify_password
from app.core.time import utc_now
from app.db.models import Admin, AdminSession
from app.services import audit

_DUMMY_HASH: str | None = None


def _burn_password_time() -> None:
    """Spend a real hashing cycle when the username is unknown, so timing is not an oracle."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(generate_token(16))
    verify_password("not-a-real-password", _DUMMY_HASH)


def authenticate(
    db: Session,
    *,
    username: str,
    password: str,
    ip: str,
    user_agent: str,
    settings: Settings,
) -> tuple[AdminSession, Admin]:
    limiter_key = f"login:{ip}:{username.lower()}"
    allowed, retry_after = login_limiter.check(
        limiter_key, settings.login_rate_limit, settings.login_rate_window_seconds
    )
    if not allowed:
        audit.record(
            db,
            action="login.rate_limited",
            actor_label=username,
            target_type="session",
            detail={"retry_after": retry_after},
            ip=ip,
            commit=True,
        )
        raise TooManyRequests(f"登录过于频繁，请 {retry_after} 秒后再试")

    admin = db.execute(select(Admin).where(Admin.username == username)).scalars().first()
    if admin is None:
        _burn_password_time()
        audit.record(
            db,
            action="login.failed",
            actor_label=username,
            detail={"reason": "unknown_user"},
            ip=ip,
            commit=True,
        )
        raise Unauthorized("用户名或密码错误")

    now = utc_now()
    if admin.locked_until and admin.locked_until > now:
        remaining = int((admin.locked_until - now).total_seconds() // 60) + 1
        raise Forbidden(f"账户已锁定，请 {remaining} 分钟后再试")
    if not admin.is_active:
        raise Forbidden("该账户已被停用")

    if not verify_password(password, admin.password_hash):
        admin.failed_login_count += 1
        detail: dict = {"reason": "bad_password", "failed": admin.failed_login_count}
        if admin.failed_login_count >= settings.max_failed_logins:
            admin.locked_until = now + settings.lockout_duration
            admin.failed_login_count = 0
            detail["locked_minutes"] = settings.lockout_minutes
        audit.record(
            db,
            action="login.failed",
            actor_label=username,
            target_type="admin",
            target_id=str(admin.id),
            detail=detail,
            ip=ip,
        )
        db.commit()
        if "locked_minutes" in detail:
            raise Forbidden(f"连续登录失败，账户锁定 {settings.lockout_minutes} 分钟")
        raise Unauthorized("用户名或密码错误")

    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = now
    admin.last_login_ip = ip

    session = open_session(db, admin, ip=ip, user_agent=user_agent, settings=settings)
    actor = Principal(
        admin_id=admin.id,
        username=admin.username,
        display_name=admin.display_name or admin.username,
        role=admin.role,
        session_id=session.id,
    )
    audit.record(db, action="login.success", actor=actor, target_type="session", target_id=session.id, ip=ip)
    db.commit()
    return session, admin


def open_session(db: Session, admin: Admin, *, ip: str, user_agent: str, settings: Settings) -> AdminSession:
    """One live session per administrator: opening a session revokes that account's earlier ones."""
    now = utc_now()
    db.execute(update(AdminSession).where(AdminSession.admin_id == admin.id).values(revoked_at=now))
    session = AdminSession(
        id=generate_token(32),
        admin_id=admin.id,
        username=admin.username,
        csrf_token=generate_token(24),
        created_at=now,
        last_seen_at=now,
        expires_at=now + settings.session_ttl,
        ip=ip,
        user_agent=user_agent[:200],
    )
    db.add(session)
    db.flush()
    return session


def close_session(db: Session, session: AdminSession, *, actor: Principal | None, ip: str) -> None:
    session.revoked_at = utc_now()
    audit.record(db, action="logout", actor=actor, target_type="session", target_id=session.id, ip=ip)
    db.commit()


def list_sessions(db: Session, *, include_revoked: bool = False, current_id: str = "") -> list[dict]:
    stmt = select(AdminSession)
    if not include_revoked:
        stmt = stmt.where(AdminSession.revoked_at.is_(None), AdminSession.expires_at > utc_now())
    rows = db.execute(stmt.order_by(AdminSession.last_seen_at.desc())).scalars().all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "expires_at": row.expires_at,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "revoked_at": row.revoked_at,
            "current": row.id == current_id,
        }
        for row in rows
    ]


def revoke(db: Session, session_id: str, *, actor: Principal, ip: str) -> AdminSession:
    session = db.get(AdminSession, session_id)
    if session is None:
        raise NotFound("会话不存在")
    if session.revoked_at is None:
        session.revoked_at = utc_now()
        audit.record(
            db,
            action="session.revoked",
            actor=actor,
            target_type="session",
            target_id=session.id,
            detail={"username": session.username},
            ip=ip,
        )
        db.commit()
    return session


def revoke_all_for(db: Session, admin_id: int, *, actor: Principal, ip: str, keep: str = "") -> int:
    stmt = update(AdminSession).where(
        AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None)
    ).values(revoked_at=utc_now())
    if keep:
        stmt = stmt.where(AdminSession.id != keep)
    count = db.execute(stmt).rowcount
    audit.record(
        db,
        action="session.revoked_all",
        actor=actor,
        target_type="admin",
        target_id=str(admin_id),
        detail={"count": count},
        ip=ip,
    )
    db.commit()
    return int(count or 0)


def prune_expired(db: Session, *, grace_days: int = 1) -> int:
    cutoff = utc_now() - timedelta(days=max(0, grace_days))
    removed = db.execute(
        delete(AdminSession).where(or_(AdminSession.expires_at < cutoff, AdminSession.revoked_at < cutoff))
    ).rowcount
    db.commit()
    return int(removed or 0)


def change_own_password(db: Session, admin: Admin, *, current: str, new: str, settings: Settings) -> AdminSession:
    if not verify_password(current, admin.password_hash):
        raise Unauthorized("当前密码不正确")
    admin.password_hash = hash_password(new)
    session = open_session(db, admin, ip=admin.last_login_ip or "", user_agent="password-change", settings=settings)
    db.commit()
    return session


def commit_unique_username(db: Session) -> None:
    """Translate the username UNIQUE constraint into a client-facing conflict."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "username" in str(exc) or "UNIQUE" in str(exc).upper():
            raise Conflict("该用户名已存在") from exc
        raise
