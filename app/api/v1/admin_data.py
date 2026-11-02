"""Audit trail queries, data export and housekeeping."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.core.deps import CsrfProtected, Dangerous, DbSession, Manager
from app.schemas.common import Page
from app.schemas.stats import AuditLogOut
from app.services import audit, auth, export

router = APIRouter(prefix="/admin", tags=["admin-data"], dependencies=[CsrfProtected])


def _csv(filename: str, generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/audit-logs", response_model=Page[AuditLogOut])
async def list_audit_logs(
    _: Manager,
    db: DbSession,
    q: str = Query(default="", max_length=80),
    action: str = Query(default="", max_length=48),
    actor: str = Query(default="", max_length=64),
    date_from: str = Query(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$", description="YYYY-MM-DD"),
    date_to: str = Query(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$", description="YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    rows, total = audit.query(
        db, q=q.strip(), action=action, actor=actor, date_from=date_from, date_to=date_to,
        page=page, page_size=page_size,
    )
    return {
        "items": rows,
        "meta": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
    }


@router.get("/audit-actions")
async def audit_actions(_: Manager, db: DbSession) -> dict:
    return {"actions": audit.distinct_actions(db)}


@router.get("/export/activities.csv")
async def export_activities(_: Manager, db: DbSession) -> StreamingResponse:
    return _csv("activities.csv", export.activities_csv(db))


@router.get("/export/rolls.csv")
async def export_rolls(
    _: Manager,
    db: DbSession,
    activity_id: str = Query(default="", max_length=32),
    status: str = Query(default="all", pattern="^(valid|void|all)$"),
) -> StreamingResponse:
    return _csv(
        f"rolls-{activity_id[:8] or 'all'}.csv",
        export.rolls_csv(db, activity_id=activity_id or None, status=status),
    )


@router.get("/export/audit.csv")
async def export_audit(_: Manager, db: DbSession) -> StreamingResponse:
    return _csv("audit-log.csv", export.audit_csv(db))


@router.get("/export/snapshot.json")
async def export_snapshot(_: Manager, db: DbSession) -> Response:
    return Response(
        content=export.snapshot_json(db),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''team-roll-snapshot.json"},
    )


@router.post("/maintenance/sessions/cleanup")
async def cleanup_sessions(actor: Dangerous, request: Request, db: DbSession) -> dict:
    removed = auth.prune_expired(db, grace_days=1)
    audit.record(
        db,
        action="maintenance.session_cleanup",
        actor=actor,
        detail={"removed": removed},
        ip=request.state.client_ip,
        commit=True,
    )
    return {"message": f"清理过期会话 {removed} 条", "removed": removed}


@router.post("/maintenance/audit/purge")
async def purge_audit(
    actor: Dangerous,
    request: Request,
    db: DbSession,
    days: int = Query(default=90, ge=7, le=3650),
) -> dict:
    removed = audit.purge_older_than(db, days)
    audit.record(
        db,
        action="maintenance.audit_purge",
        actor=actor,
        detail={"days": days, "removed": removed},
        ip=request.state.client_ip,
        commit=True,
    )
    return {"message": f"清理 {days} 天前的审计日志 {removed} 条", "removed": removed}
