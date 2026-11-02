"""WebSocket endpoint for live activity updates."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import client_ip_from_headers
from app.services import activity as activity_service
from app.services import roll as roll_service

router = APIRouter(tags=["realtime"])
logger = logging.getLogger("team_roll.ws")

POLICY_VIOLATION = 1008


@router.websocket("/ws/{activity_id}")
async def activity_socket(websocket: WebSocket, activity_id: str) -> None:
    settings = get_settings()
    manager = websocket.app.state.ws_manager

    db = websocket.app.state.session_factory()
    try:
        try:
            activity_service.get_or_404(db, activity_id)  # reject sockets for unknown or deleted activities
            snapshot = activity_service.detail(db, activity_id)
            rolls = roll_service.list_serialized(db, activity_id, status="valid")
        except AppError:
            await websocket.close(code=POLICY_VIOLATION, reason="活动不存在或已被删除")
            return
    finally:
        db.close()

    if not await manager.connect(websocket, activity_id):
        return

    peer = websocket.client.host if websocket.client else "unknown"
    ip = client_ip_from_headers(
        list(websocket.headers.items()), trust_proxy_headers=settings.trust_proxy_headers, fallback=peer
    )
    logger.info("WebSocket 连接建立 activity=%s ip=%s", activity_id, ip)

    try:
        await manager.send_personal(
            websocket,
            {
                "type": "hello",
                "activity": snapshot,
                "rolls": rolls,
                "connections": manager.connections_for(activity_id),
            },
        )
        while True:
            frame = await websocket.receive_json()
            if frame.get("type") == "ping":
                await manager.send_personal(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - abnormal transport failure
        logger.warning("WebSocket 异常断开 activity=%s ip=%s", activity_id, ip, exc_info=True)
    finally:
        manager.disconnect(websocket, activity_id)
        logger.debug("WebSocket 连接关闭 activity=%s ip=%s", activity_id, ip)
