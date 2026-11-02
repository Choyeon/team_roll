"""Dashboard aggregates and runtime/system information."""

from __future__ import annotations

import platform
import time
from pathlib import Path

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import __version__ as APP_VERSION
from app.core.config import get_settings
from app.core.deps import DbSession, Reader
from app.core.time import utc_now
from app.db.models import Activity, Admin, AdminSession, AuditLog, RollResult
from app.services import stats as stats_service

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])

STARTED_AT = time.monotonic()


@router.get("/dashboard")
async def dashboard(
    _: Reader,
    db: DbSession,
    request: Request,
    tz_offset_minutes: int = Query(default=0, ge=-840, le=840, description="浏览器相对 UTC 的分钟偏移"),
    trend_days: int = Query(default=14, ge=1, le=60),
) -> dict:
    manager = request.app.state.ws_manager
    return stats_service.dashboard(
        db,
        tz_offset_minutes=tz_offset_minutes,
        trend_days=trend_days,
        live_connections=manager.total,
    )


@router.get("/dashboard/rooms")
async def live_rooms(_: Reader, request: Request) -> dict:
    return {"rooms": request.app.state.ws_manager.rooms(), "total": request.app.state.ws_manager.total}


@router.get("/system")
async def system_info(_: Reader, db: DbSession, request: Request) -> dict:
    settings = get_settings()
    tables = {}
    for model in (Activity, RollResult, Admin, AdminSession, AuditLog):
        tables[model.__tablename__] = int(db.execute(select(func.count(model.id))).scalar_one() or 0)

    size = 0
    if settings.database_url.startswith("sqlite"):
        raw_path = settings.database_url.split("///")[-1] or ""
        path = Path(raw_path)
        if path.is_file():
            size = path.stat().st_size

    return {
        "app_name": settings.app_name,
        "version": APP_VERSION,
        "environment": settings.environment,
        "debug": settings.debug,
        "python_version": platform.python_version(),
        "server_time": utc_now().isoformat(),
        "uptime_seconds": round(time.monotonic() - STARTED_AT, 1),
        "websocket_connections": request.app.state.ws_manager.total,
        "session_ttl_minutes": settings.session_ttl_minutes,
        "rate_limits": {
            "login_per_window": settings.login_rate_limit,
            "login_window_seconds": settings.login_rate_window_seconds,
            "roll_per_window": settings.roll_rate_limit,
            "roll_window_seconds": settings.roll_rate_window_seconds,
        },
        "database": {
            "url_scheme": settings.database_url.split("://")[0],
            "file_size_bytes": size,
            "tables": tables,
        },
    }


