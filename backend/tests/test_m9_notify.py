"""M9 消息与提醒 验收测试（负责人 A）。

覆盖：M9-01 站内消息中心 + 未读红点、M9-02/03/04 端能力如实标注、M9-06 免打扰。
"""
from __future__ import annotations

import pytest

CONDITIONS = {"capital": 30000, "dailyHours": 2, "city": "杭州市"}


async def _pay_something(client, drain):
    task_id = (await client.post("/api/diagnose", json=CONDITIONS)).json()["data"]["taskId"]
    await drain()
    locked_id = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]["locked"]["id"]
    created = (
        await client.post(
            "/api/payment/create", json={"plan": "single", "platform": "web", "matchId": locked_id}
        )
    ).json()["data"]
    await client.post(
        "/api/payment/callback/alipay",
        json={"order_id": created["orderId"], "result": "success"},
    )
    return created["orderId"]


async def test_message_center_and_unread(client, drain):
    order_id = await _pay_something(client, drain)

    data = (await client.get("/api/notify/messages")).json()["data"]
    assert data["total"] >= 1
    assert data["unread"] >= 1
    first = data["items"][0]
    assert first["category"] == "order"
    assert first["categoryLabel"] == "订单通知"
    assert first["isRead"] is False
    assert "支付成功" in first["title"]
    assert order_id in (first["link"] or "")

    unread = (await client.get("/api/notify/unread")).json()["data"]["unread"]
    assert unread >= 1

    marked = (await client.post("/api/notify/read")).json()["data"]
    assert marked["updated"] >= 1
    assert marked["unread"] == 0

    assert (await client.get("/api/notify/unread")).json()["data"]["unread"] == 0


async def test_mark_single_message_read(client, drain):
    await _pay_something(client, drain)
    items = (await client.get("/api/notify/messages")).json()["data"]["items"]
    target = items[0]["id"]
    data = (await client.post("/api/notify/read", params={"id": target})).json()["data"]
    assert data["updated"] == 1

    refreshed = (await client.get("/api/notify/messages")).json()["data"]["items"]
    read_ids = {i["id"] for i in refreshed if i["isRead"]}
    assert target in read_ids


async def test_category_filter_and_paging(client, drain):
    await _pay_something(client, drain)
    only_activity = (
        await client.get("/api/notify/messages", params={"category": "activity"})
    ).json()["data"]
    assert only_activity["total"] == 0

    paged = (await client.get("/api/notify/messages", params={"page": 1, "pageSize": 1})).json()["data"]
    assert paged["page"] == 1
    assert paged["pageSize"] == 1
    assert len(paged["items"]) <= 1


async def test_subscribe_marks_web_limitation_honestly(client):
    data = (await client.get("/api/notify/subscribe", params={"platform": "web"})).json()["data"]
    assert data["platform"] == "web"
    by_key = {i["key"]: i for i in data["items"]}
    # Web 端不支持后台通知，必须如实标注，不能误导用户
    # 注意：i["key"] 是稳定的「能力标识」（如 service_notice），不属于响应字段名，
    # 因此不参与 camelCase 转换。
    assert by_key["service_notice"]["supported"] is False
    assert by_key["app_push"]["supported"] is False
    assert by_key["desktop_notice"]["supported"] is False
    assert "网页版" in data["notice"]

    weapp = (await client.get("/api/notify/subscribe", params={"platform": "weapp"})).json()["data"]
    assert {i["key"]: i for i in weapp["items"]}["service_notice"]["supported"] is True


async def test_settings_default_and_update(client):
    data = (await client.get("/api/notify/settings")).json()["data"]
    assert data["dndEnabled"] is True
    assert data["dndStart"] == "22:00"
    assert data["dndEnd"] == "08:00"
    assert data["marketReminder"] is True

    updated = (
        await client.put(
            "/api/notify/settings",
            json={"dndEnabled": False, "marketReminder": False, "appPush": False},
        )
    ).json()["data"]
    assert updated["dndEnabled"] is False
    assert updated["marketReminder"] is False
    assert updated["appPush"] is False

    bad = (
        await client.put("/api/notify/settings", json={"dndStart": "25:99"})
    ).json()
    assert bad["code"] == 40001


def test_dnd_logic_unit():
    """M9-06：免打扰时段内不推送营销消息，交易类消息不受影响。"""
    from app.models import NotifySetting
    from app.services.notify import in_dnd, should_push
    from datetime import datetime

    setting = NotifySetting(
        id="x", owner_key="guest:t", dnd_enabled=True, dnd_start="22:00", dnd_end="08:00"
    )
    assert in_dnd(setting, datetime(2026, 10, 4, 23, 30)) is True
    assert in_dnd(setting, datetime(2026, 10, 4, 7, 0)) is True
    assert in_dnd(setting, datetime(2026, 10, 4, 12, 0)) is False
    # 营销类被拦截
    assert should_push(setting, "activity", datetime(2026, 10, 4, 23, 30)) is False
    # 交易类照常
    assert should_push(setting, "order", datetime(2026, 10, 4, 23, 30)) is True

    setting.dnd_enabled = False
    assert in_dnd(setting, datetime(2026, 10, 4, 23, 30)) is False
