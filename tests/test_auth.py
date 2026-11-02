"""Auth, session, password and CSRF behaviour."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.deps import SESSION_TOUCH_SECONDS
from app.core.time import utc_now
from app.db.models import AdminSession
from app.db.session import get_sessionmaker

PASSWORD = "another-secret-password"
NEW_PASSWORD = "rotated-secret-password"


def test_login_rejects_wrong_password(anon_client):
    response = anon_client.post("/api/v1/auth/login", json={"username": "boss", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_login_rejects_unknown_user(anon_client):
    response = anon_client.post("/api/v1/auth/login", json={"username": "ghost", "password": "whatever-123"})
    assert response.status_code == 401


def test_me_requires_session(anon_client):
    assert anon_client.get("/api/v1/auth/me").status_code == 401


def test_logout_is_idempotent_for_anonymous(anon_client):
    assert anon_client.post("/api/v1/auth/logout").status_code == 200


def test_admin_write_needs_the_csrf_header(login_as):
    client = login_as()
    csrf = client.get("/api/v1/auth/me").json()["csrf_token"]
    del client.headers["X-CSRF-Token"]
    blocked = client.post("/api/v1/admin/activities", json={"name": "缺少 CSRF", "roll_min": 1, "roll_max": 6})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "forbidden"

    client.headers["X-CSRF-Token"] = csrf
    allowed = client.post("/api/v1/admin/activities", json={"name": "带 CSRF", "roll_min": 1, "roll_max": 6})
    assert allowed.status_code == 201, allowed.text
    client.delete(f"/api/v1/admin/activities/{allowed.json()['id']}")


def test_sessions_are_listed_and_kicked(login_as):
    client = login_as()
    username = client.get("/api/v1/auth/me").json()["username"]
    sessions = client.get("/api/v1/admin/sessions").json()
    mine = [item for item in sessions if item["username"] == username]
    assert mine, "登录会话应出现在在线列表中"

    assert client.delete(f"/api/v1/admin/sessions/{mine[0]['id']}").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_stale_session_touch_refreshes_the_sliding_expiry(login_as):
    """An authenticated call after the touch window must extend the TTL, not fail."""
    client = login_as()
    session_id = client.cookies.get("session_id")
    settings = get_settings()

    with get_sessionmaker()() as db:
        session = db.get(AdminSession, session_id)
        session.last_seen_at = utc_now() - timedelta(seconds=SESSION_TOUCH_SECONDS + 1)
        db.commit()

    assert client.get("/api/v1/auth/me").status_code == 200

    with get_sessionmaker()() as db:
        refreshed = db.get(AdminSession, session_id)
        drift = abs((refreshed.expires_at - refreshed.last_seen_at) - settings.session_ttl)
        assert drift < timedelta(seconds=5), "滑动续期应以 TTL 重新计算过期时间"


def test_logout_clears_the_session(login_as):
    client = login_as()
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_new_login_revokes_the_previous_session(login_as, app):
    """One live session per admin: a second login signs the first one out."""
    client = login_as()
    username = client.get("/api/v1/auth/me").json()["username"]

    with TestClient(app) as other:
        assert other.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
        assert other.get("/api/v1/auth/me").status_code == 200


def test_password_change_takes_effect_immediately(login_as, app):
    client = login_as()
    username = client.get("/api/v1/auth/me").json()["username"]
    changed = client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert changed.status_code == 200, changed.text

    with TestClient(app) as outsider:
        assert outsider.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD}).status_code == 401
        assert (
            outsider.post("/api/v1/auth/login", json={"username": username, "password": NEW_PASSWORD}).status_code == 200
        )


def test_wrong_current_password_is_refused(login_as):
    client = login_as()
    response = client.post(
        "/api/v1/auth/password", json={"current_password": "not-the-password", "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 401


def test_weak_new_password_is_rejected(login_as):
    client = login_as()
    response = client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert response.status_code == 422


def test_repeated_failures_lock_the_account(login_as, app):
    from app.core.config import get_settings

    client = login_as()
    username = client.get("/api/v1/auth/me").json()["username"]

    with TestClient(app) as outsider:
        responses = []
        for _ in range(get_settings().max_failed_logins + 1):
            responses.append(
                outsider.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password"})
            )
        assert [item.status_code for item in responses].count(403) >= 1
        locked = outsider.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert locked.status_code == 403
        assert "锁定" in locked.json()["error"]["message"]
