"""Realtime fan-out for activity pages.

Send failures are isolated per connection: one dead socket must not stop the
broadcast to the rest of the room, and must not bubble into the HTTP request
that triggered it.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger("team_roll.ws")


async def _send(websocket: WebSocket, message: dict) -> None:
    """Send ``message`` exactly as the HTTP API would encode it.

    Service payloads contain ``datetime`` values; Starlette's ``send_json`` uses
    a plain ``json.dumps`` and would raise after the socket is already accepted.
    """
    await websocket.send_text(json.dumps(jsonable_encoder(message), ensure_ascii=False))


class ConnectionManager:
    def __init__(self, *, max_per_activity: int = 500) -> None:
        self._groups: dict[str, set[WebSocket]] = {}
        self._max_per_activity = max_per_activity

    async def connect(self, websocket: WebSocket, activity_id: str) -> bool:
        room = self._groups.setdefault(activity_id, set())
        if len(room) >= self._max_per_activity:
            await websocket.close(code=1013, reason="room is full")
            return False
        await websocket.accept()
        room.add(websocket)
        return True

    def disconnect(self, websocket: WebSocket, activity_id: str) -> None:
        room = self._groups.get(activity_id)
        if room is None:
            return
        room.discard(websocket)
        if not room:
            self._groups.pop(activity_id, None)

    async def broadcast(self, activity_id: str, message: dict) -> int:
        room = list(self._groups.get(activity_id, ()))
        if not room:
            return 0
        results = await asyncio.gather(*(_send(connection, message) for connection in room), return_exceptions=True)
        dead = [connection for connection, outcome in zip(room, results, strict=True) if isinstance(outcome, Exception)]
        for connection in dead:
            self.disconnect(connection, activity_id)
        if dead:
            logger.debug("清理 %d 个失效 WebSocket 连接（活动 %s）", len(dead), activity_id)
        return len(room) - len(dead)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        try:
            await _send(websocket, message)
        except Exception:  # pragma: no cover - client vanished mid-send
            logger.debug("个人消息发送失败", exc_info=True)

    def connections_for(self, activity_id: str) -> int:
        return len(self._groups.get(activity_id, ()))

    @property
    def total(self) -> int:
        return sum(len(room) for room in self._groups.values())

    def rooms(self) -> dict[str, int]:
        return {activity_id: len(room) for activity_id, room in self._groups.items() if room}
