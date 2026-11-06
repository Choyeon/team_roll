"""Roll drawing, quotas, and the admin corrections that used to hit the wrong row."""

from __future__ import annotations

PREFIX = "/api/v1"


def create_activity(admin_client, **overrides):
    payload = {"name": "范围活动", "description": "", "roll_min": 1, "roll_max": 4, "max_participations": 1}
    payload.update(overrides)
    response = admin_client.post(f"{PREFIX}/admin/activities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_roll_numbers_stay_inside_the_range_and_unique(admin_client):
    activity_id = create_activity(admin_client)
    numbers = []
    for name in ("阿明", "阿强", "小红"):
        response = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": name})
        assert response.status_code == 201, response.text
        numbers.append(response.json()["roll"]["number"])
    assert len(set(numbers)) == 3
    assert all(1 <= value <= 4 for value in numbers)
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_repeat_participant_is_rejected_until_quota_allows(admin_client):
    activity_id = create_activity(admin_client, max_participations=1)
    assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "重复者"}).status_code == 201
    second = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "重复者"})
    assert second.status_code == 409
    assert "参与过" in second.json()["error"]["message"]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_participant_cap_blocks_new_names_only(admin_client):
    activity_id = create_activity(
        admin_client, roll_min=1, roll_max=10, max_participations=2, max_participants=2
    )
    for name in ("甲", "乙"):
        assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": name}).status_code == 201

    # 已经上榜的人仍可用完自己的次数，被挡住的是第 3 个新名字。
    assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "甲"}).status_code == 201
    blocked = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "丙"})
    assert blocked.status_code == 409
    assert "名额已满" in blocked.json()["error"]["message"]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_voiding_every_record_of_a_name_frees_its_slot(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10, max_participants=1)
    first = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "占位者"})
    assert first.status_code == 201
    assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "后来者"}).status_code == 409

    roll_id = first.json()["roll"]["id"]
    assert admin_client.put(f"{PREFIX}/admin/rolls/{roll_id}/void", json={"reason": "误操作"}).status_code == 200
    assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "后来者"}).status_code == 201
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_uncapped_activity_accepts_new_names(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10, max_participants=0)
    for index in range(3):
        response = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": f"队友{index}"})
        assert response.status_code == 201
        assert response.json()["activity"]["max_participants"] == 0
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_range_exhaustion_reports_conflict(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=2)
    for name in ("甲", "乙"):
        assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": name}).status_code == 201
    blocked = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "丙"})
    assert blocked.status_code == 409
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_voiding_frees_the_number_for_the_next_player(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=2)
    first = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "首位"}).json()["roll"]
    void = admin_client.put(f"{PREFIX}/admin/rolls/{first['id']}/void", json={"reason": "误操作"})
    assert void.status_code == 200
    assert void.json()["status"] == "void"
    assert void.json()["void_reason"] == "误操作"

    replacement = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "替补"})
    assert replacement.status_code == 201

    last = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "再试"})
    assert last.status_code == 201
    # Voiding released the first number, so the whole 1-2 range could be refilled.
    assert {replacement.json()["roll"]["number"], last.json()["roll"]["number"]} == {1, 2}
    assert admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "第三人"}).status_code == 409
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_void_can_be_restored(admin_client):
    activity_id = create_activity(admin_client)
    roll = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "恢复测试"}).json()["roll"]
    admin_client.put(f"{PREFIX}/admin/rolls/{roll['id']}", json={"reason": "临时作废"})
    restored = admin_client.put(f"{PREFIX}/admin/rolls/{roll['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "valid"
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_restore_is_blocked_when_the_number_was_taken(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=1)
    first = admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": "首位"}).json()["roll"]
    admin_client.put(f"{PREFIX}/admin/rolls/{first['id']}/void", json={"reason": "作废"})
    admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": "补录", "number": 1})
    clash = admin_client.put(f"{PREFIX}/admin/rolls/{first['id']}/restore")
    assert clash.status_code == 409
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_admin_targets_rolls_by_id_not_by_list_position(admin_client):
    """The 1.x delete route indexed the leaderboard and removed the wrong record."""
    activity_id = create_activity(admin_client, roll_min=1, roll_max=4)
    ids = []
    for name in ("一号", "二号", "三号"):
        ids.append(admin_client.post(f"{PREFIX}/activities/{activity_id}/rolls", json={"name": name}).json()["roll"]["id"])

    remaining = {item["id"] for item in admin_client.get(f"{PREFIX}/activities/{activity_id}/rolls").json()}
    assert remaining == set(ids)

    deleted = admin_client.delete(f"{PREFIX}/admin/rolls/{ids[1]}")
    assert deleted.status_code == 200
    after = {item["id"] for item in admin_client.get(f"{PREFIX}/activities/{activity_id}/rolls").json()}
    assert after == {ids[0], ids[2]}
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_manual_entry_and_rename(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10)
    created = admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": "补录者", "number": 7})
    assert created.status_code == 201, created.text
    roll_id = created.json()["id"]

    renamed = admin_client.patch(f"{PREFIX}/admin/rolls/{roll_id}", json={"name": "改名后"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "改名后"

    clash = admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": "撞号", "number": 7})
    assert clash.status_code == 409

    out_of_range = admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": "越界", "number": 99})
    assert out_of_range.status_code == 400
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_ranking_is_dense_and_descending(admin_client):
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10)
    for name, number in (("低", 2), ("中", 5), ("高", 9)):
        admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": name, "number": number})
    rolls = admin_client.get(f"{PREFIX}/activities/{activity_id}/rolls", params={"order": "number"}).json()
    assert [roll["rank"] for roll in rolls] == [1, 2, 3]
    assert [roll["number"] for roll in rolls] == [9, 5, 2]
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_admin_roll_list_is_an_envelope_with_admin_fields(admin_client):
    """The management screen reads ``rolls`` out of the envelope, not the body itself."""
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10)
    admin_client.post(f"{PREFIX}/admin/activities/{activity_id}/rolls", json={"name": "补录者", "number": 4})

    payload = admin_client.get(f"{PREFIX}/admin/activities/{activity_id}/rolls", params={"status": "valid"}).json()
    assert set(payload) == {"activity", "stats", "rolls"}
    assert payload["activity"]["id"] == activity_id
    assert payload["rolls"][0]["created_by"]
    assert "ip" in payload["rolls"][0]

    voided = admin_client.get(f"{PREFIX}/admin/activities/{activity_id}/rolls", params={"status": "void"}).json()
    assert voided["rolls"] == []
    admin_client.delete(f"{PREFIX}/admin/activities/{activity_id}")


def test_player_agent_reaches_admins_only(admin_client):
    """Same-office players share an exit IP, so the browser signature is what separates them."""
    activity_id = create_activity(admin_client, roll_min=1, roll_max=10)
    admin_client.post(
        f"{PREFIX}/activities/{activity_id}/rolls",
        json={"name": "签名玩家"},
        headers={"user-agent": "Mozilla/5.0   TestBrowser/1.0"},
    )

    admin_row = admin_client.get(f"{PREFIX}/admin/activities/{activity_id}/rolls").json()["rolls"][0]
    assert admin_row["user_agent"] == "Mozilla/5.0 TestBrowser/1.0"

    public_row = admin_client.get(f"{PREFIX}/activities/{activity_id}/rolls").json()[0]
    assert "user_agent" not in public_row
    assert "ip" not in public_row
    admin_client.delete(f"{PREFIX}/activities/{activity_id}")
