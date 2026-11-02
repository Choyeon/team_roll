"""Realtime channel against a live server.

Starlette's TestClient cannot issue an HTTP request while a WebSocket context from the
same client is open (one portal, one loop), and a broadcast from a second client would
land on a different loop. A real uvicorn instance keeps the socket and the triggering
request in the same loop, which is also how the feature runs in production.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

PREFIX = "/api/v1"


class _Server(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.port = _free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on")
        )

    def run(self):
        self.server.run()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws_base(self) -> str:
        return f"ws://127.0.0.1:{self.port}"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def live(app):
    thread = _Server(app)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"{thread.base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        pytest.fail("uvicorn 测试服务未在 15 秒内就绪")
    yield thread
    thread.server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def http(live, admin_client):
    """Plain httpx client carrying the run's superuser session + CSRF double submit."""
    with httpx.Client(
        base_url=live.base,
        cookies={"session_id": admin_client.cookies.get("session_id")},
        headers={"X-CSRF-Token": admin_client.headers["X-CSRF-Token"]},
    ) as client:
        yield client


def make_activity(http, name: str, **overrides) -> str:
    payload = {"name": name, "description": "", "roll_min": 1, "roll_max": 20, "max_participations": 20}
    payload.update(overrides)
    response = http.post(f"{PREFIX}/admin/activities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_socket_sends_snapshot_then_broadcasts(live, http):
    activity_id = make_activity(http, "实时通道")
    with connect(f"{live.ws_base}/ws/{activity_id}") as socket_io:
        hello = json.loads(socket_io.recv(timeout=10))
        assert hello["type"] == "hello"
        assert hello["activity"]["id"] == activity_id
        assert hello["rolls"] == []
        assert hello["connections"] == 1
        # Frames must already be JSON-safe; raw datetime values silently killed the socket.
        assert isinstance(hello["activity"]["created_at"], str)

        rolled = http.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "实时玩家"})
        assert rolled.status_code == 201, rolled.text

        message = json.loads(socket_io.recv(timeout=10))
        assert message["type"] == "roll_result"
        assert message["result"]["name"] == "实时玩家"
        assert message["result"]["rank"] == 1

        socket_io.send(json.dumps({"type": "ping"}))
        assert json.loads(socket_io.recv(timeout=10)) == {"type": "pong"}

    assert http.delete(f"{PREFIX}/admin/activities/{activity_id}").status_code == 200


def test_socket_refuses_unknown_activity(live):
    # Closing before accept() makes uvicorn answer the handshake with 403.
    with pytest.raises(InvalidStatus) as refused, connect(f"{live.ws_base}/ws/does-not-exist", close_timeout=5):
        pass
    assert "403" in str(refused.value)


def test_deleting_the_activity_is_broadcast(live, http):
    activity_id = make_activity(http, "将被删除", roll_min=1, roll_max=5)
    with connect(f"{live.ws_base}/ws/{activity_id}") as socket_io:
        assert json.loads(socket_io.recv(timeout=10))["type"] == "hello"
        assert http.delete(f"{PREFIX}/admin/activities/{activity_id}").status_code == 200
        assert json.loads(socket_io.recv(timeout=10))["type"] == "activity_deleted"


def test_void_restore_and_delete_are_broadcast(live, http):
    activity_id = make_activity(http, "作废广播")
    with connect(f"{live.ws_base}/ws/{activity_id}") as socket_io:
        assert json.loads(socket_io.recv(timeout=10))["type"] == "hello"
        roll = http.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "玩家"}).json()["roll"]
        assert json.loads(socket_io.recv(timeout=10))["type"] == "roll_result"

        voided = http.put(f"{PREFIX}/admin/rolls/{roll['id']}/void", json={"reason": "误操作"})
        assert voided.status_code == 200, voided.text
        message = json.loads(socket_io.recv(timeout=10))
        assert message["type"] == "roll_updated"
        assert message["result"]["status"] == "void"

        restored = http.put(f"{PREFIX}/admin/rolls/{roll['id']}/restore")
        assert restored.status_code == 200, restored.text
        message = json.loads(socket_io.recv(timeout=10))
        assert message["type"] == "roll_updated"
        assert message["result"]["status"] == "valid"

        removed = http.delete(f"{PREFIX}/admin/rolls/{roll['id']}")
        assert removed.status_code == 200, removed.text
        message = json.loads(socket_io.recv(timeout=10))
        assert message == {"type": "roll_deleted", "result_id": roll["id"]}

    assert http.delete(f"{PREFIX}/admin/activities/{activity_id}").status_code == 200
