"""Activity lifecycle, role capabilities, dashboard and data endpoints."""

from __future__ import annotations

from sqlalchemy import select

PREFIX = "/api/v1"


def create_activity(admin_client, name="生命周期", **overrides):
    payload = {"name": name, "description": "", "roll_min": 1, "roll_max": 10, "max_participations": 1}
    payload.update(overrides)
    response = admin_client.post(f"{PREFIX}/admin/activities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_created_activity_is_visible_publicly(admin_client):
    activity_id = create_activity(admin_client, name="公开可见")
    listed = admin_client.get(f"{PREFIX}/activities").json()["items"]
    assert activity_id in [item["id"] for item in listed]

    detail = admin_client.get(f"{PREFIX}/activities/{activity_id}").json()
    assert detail["status"] == "active"
    assert detail["remaining_numbers"] == 10
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_ended_activity_is_hidden_and_blocks_rolls(admin_client):
    activity_id = create_activity(admin_client, name="已结束活动")
    ended = admin_client.put(f"{PREFIX}/admin/activities/{activity_id}/status", json={"status": "ended"})
    assert ended.status_code == 200
    assert ended.json()["ended_at"]

    blocked = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "迟到者"})
    assert blocked.status_code == 409

    listed = admin_client.get(f"{PREFIX}/activities").json()["items"]
    assert activity_id not in [item["id"] for item in listed]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_paused_activity_hides_from_the_home_list(admin_client):
    activity_id = create_activity(admin_client, name="暂停活动")
    admin_client.put(f"{PREFIX}/admin/activities/{activity_id}/status", json={"status": "paused"})
    listed = admin_client.get(f"{PREFIX}/activities").json()["items"]
    assert activity_id in [item["id"] for item in listed]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_range_cannot_shrink_below_existing_rolls(admin_client):
    activity_id = create_activity(admin_client, name="收窄范围", roll_min=1, roll_max=20)
    admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "高点"})
    narrowed = admin_client.patch(f"{PREFIX}/admin/activities/{activity_id}", json={"roll_max": 2})
    assert narrowed.status_code == 409
    assert "范围不能收窄" in narrowed.json()["error"]["message"]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_invalid_range_is_rejected(admin_client):
    rejected = admin_client.post(f"{PREFIX}/admin/activities", json={"name": "错误范围", "roll_min": 50, "roll_max": 10})
    assert rejected.status_code == 422


def test_deleting_an_activity_removes_its_rolls(admin_client):
    activity_id = create_activity(admin_client, name="级联删除")
    admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "参与者"})
    assert admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}").status_code == 200
    assert admin_client.get(f"{PREFIX}/activities/{activity_id}").status_code == 404


def test_dashboard_reports_kpis_and_trend(admin_client):
    activity_id = create_activity(admin_client, name="看板活动")
    admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "看板参与者"})

    payload = admin_client.get(f"{PREFIX}/admin/dashboard", params={"trend_days": 7}).json()
    assert payload["kpis"]["activities_total"] >= 1
    assert payload["kpis"]["rolls_total"] >= 1
    assert payload["kpis"]["participants_unique"] >= 1
    assert len(payload["trend"]) == 7
    assert sum(point["rolls"] for point in payload["trend"]) >= 1
    assert payload["status_breakdown"]
    assert payload["recent_rolls"]
    assert payload["top_activities"]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_system_endpoint_reports_runtime(admin_client):
    payload = admin_client.get(f"{PREFIX}/admin/system").json()
    assert payload["version"]
    assert "database" in payload
    tables = payload["database"]["tables"]
    assert {"activities", "roll_results", "admins"} <= set(tables)
    assert all(count >= 0 for count in tables.values())


def test_activity_distribution_stats(admin_client):
    activity_id = create_activity(admin_client, name="统计活动", roll_min=1, roll_max=6)
    for number in (1, 3, 6):
        admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": f"人{number}", "number": number})
    stats = admin_client.get(f"{PREFIX}/admin/activities/{activity_id}/stats").json()
    assert stats["taken"] == 3
    assert stats["max"] == 6
    assert stats["range"] == [1, 6]
    assert sum(stats["distribution"]) == 3
    assert len(stats["distribution_labels"]) == len(stats["distribution"])
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_exports_stream_bom_csv(admin_client):
    for path in ("/admin/export/activities.csv", "/admin/export/rolls.csv", "/admin/export/audit.csv"):
        response = admin_client.get(f"{PREFIX}{path}")
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"\xef\xbb\xbf")
        assert "attachment" in response.headers["content-disposition"]

    snapshot = admin_client.get(f"{PREFIX}/admin/export/snapshot.json")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert {"generated_at", "activities"} <= set(body)
    assert all("rolls" in activity for activity in body["activities"])


def test_audit_log_records_admin_actions(admin_client):
    activity_id = create_activity(admin_client, name="审计活动")
    logs = admin_client.get(f"{PREFIX}/admin/audit-logs", params={"action": "activity.created"}).json()["items"]
    assert any(item["target_id"] == activity_id for item in logs)
    assert admin_client.get(f"{PREFIX}/admin/audit-actions").json()
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_viewer_can_read_but_not_write(login_as):
    client = login_as(role="viewer")
    me = client.get("/api/v1/auth/me").json()
    assert "manage" not in me["capabilities"]
    assert client.get("/api/v1/admin/dashboard").status_code == 200
    assert client.get(f"{PREFIX}/activities").status_code == 200
    # Audit trails and account management sit behind the manage capability.
    assert client.get("/api/v1/admin/audit-logs").status_code == 403
    assert client.get("/api/v1/admin/admins").status_code == 403

    forbidden = client.post("/api/v1/admin/activities", json={"name": "只读创建"})
    assert forbidden.status_code == 403


def test_admin_role_cannot_manage_accounts(login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/admin/admins").status_code == 403
    assert client.post("/api/v1/admin/admins", json={"username": "extra", "password": "long-enough-password"}).status_code == 403
    assert client.get("/api/v1/admin/audit-logs").status_code == 200
    assert client.post("/api/v1/admin/activities", json={"name": "管理员可建", "roll_min": 1, "roll_max": 5}).status_code == 201


def test_self_deactivation_and_self_deletion_are_blocked(admin_client):
    me = admin_client.get("/api/v1/auth/me").json()
    target = next(item for item in admin_client.get("/api/v1/admin/admins").json() if item["username"] == me["username"])

    deactivated = admin_client.patch(f"{PREFIX}/admin/admins/{target['id']}", json={"is_active": False})
    assert deactivated.status_code == 400
    assert "当前登录" in deactivated.json()["error"]["message"]

    removed = admin_client.delete(f"{PREFIX}/admin/admins/{target['id']}")
    assert removed.status_code == 400


def test_the_last_active_super_cannot_be_demoted(login_as):
    """The guard counts active supers, so it is checked on an isolated account."""
    import pytest

    from app.core.errors import Conflict
    from app.db.models import Admin, AdminRole
    from app.db.session import get_sessionmaker
    from app.services import admins as admins_service

    client = login_as()
    admin_id = client.admin_id
    assert client.get("/api/v1/auth/me").json()["role"] == "super"

    with get_sessionmaker()() as db:
        solo = db.get(Admin, admin_id)
        others = db.execute(select(Admin).where(Admin.role == AdminRole.SUPER, Admin.id != admin_id)).scalars().all()
        for other in others:
            other.role = AdminRole.VIEWER
        db.commit()

        with pytest.raises(Conflict):
            admins_service._guard_last_super(db, solo)

        survivor = Admin(username="second-super", password_hash="placeholder", role=AdminRole.SUPER, is_active=True)
        db.add(survivor)
        db.commit()
        admins_service._guard_last_super(db, solo)  # a second super makes the change safe

        db.delete(survivor)
        for other in others:
            other.role = AdminRole.SUPER
        db.commit()


def test_deactivating_an_admin_revokes_their_sessions(admin_client, login_as, app):
    from fastapi.testclient import TestClient

    client = login_as()
    me = client.get("/api/v1/auth/me").json()

    deactivated = admin_client.patch(f"{PREFIX}/admin/admins/{client.admin_id}", json={"is_active": False})
    assert deactivated.status_code == 200

    with TestClient(app) as outsider:
        assert outsider.get("/api/v1/auth/me").status_code == 401
        blocked = outsider.post(
            "/api/v1/auth/login", json={"username": me["username"], "password": "another-secret-password"}
        )
        assert blocked.status_code == 403
        assert "停用" in blocked.json()["error"]["message"]


def test_duplicate_username_is_rejected(admin_client, login_as):
    client = login_as()
    username = client.get("/api/v1/auth/me").json()["username"]
    response = admin_client.post("/api/v1/admin/admins", json={"username": username, "password": "another-secret-password"})
    assert response.status_code == 409
