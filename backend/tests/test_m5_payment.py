"""M5 付费与订单 验收测试（负责人 A）。

覆盖：M5-03 三档价格、M5-04 渠道适配、M5-05 订单状态机、M5-06 回调+查单双保险、M5-07 退款、幂等。
"""
from __future__ import annotations

import pytest

CONDITIONS = {"capital": 30000, "dailyHours": 2, "city": "杭州市"}


async def _prepared_order(client, drain, plan="single", platform="web"):
    task_id = (
        await client.post("/api/diagnose", json=CONDITIONS)
    ).json()["data"]["taskId"]
    await drain()
    match = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]
    locked_id = match["locked"]["id"]
    created = (
        await client.post(
            "/api/payment/create",
            json={"plan": plan, "platform": platform, "matchId": locked_id},
        )
    ).json()["data"]
    return task_id, locked_id, created


async def test_three_price_tiers(client):
    data = (await client.get("/api/payment/plans")).json()["data"]
    plans = {p["plan"]: p for p in data["plans"]}
    assert plans["single"]["priceCents"] == 2990
    assert plans["month"]["priceCents"] == 9900
    assert plans["year"]["priceCents"] == 59900
    assert plans["single"]["highlight"] is True
    assert plans["single"]["badge"] == "★ 现金流主力"
    assert all(p["rights"] for p in data["plans"])


@pytest.mark.parametrize(
    "platform,channel",
    [("web", "alipay"), ("weapp", "wechat"), ("android", "wechat"), ("ios", "apple"), ("harmony", "huawei")],
)
async def test_channel_adaptation(client, drain, platform, channel):
    _, _, created = await _prepared_order(client, drain, platform=platform)
    assert created["channel"] == channel
    assert created["payParams"]["channel"] == channel


async def test_order_state_machine_and_idempotent_callback(client, drain):
    _, locked_id, created = await _prepared_order(client, drain)
    order_id = created["orderId"]
    assert created["status"] == "pending"
    assert created["reused"] is False
    assert created["amountCents"] == 2990

    # 幂等：同用户同商机重复创建返回同一订单
    again = (
        await client.post(
            "/api/payment/create",
            json={"plan": "single", "platform": "web", "matchId": locked_id},
        )
    ).json()["data"]
    assert again["orderId"] == order_id
    assert again["reused"] is True

    # 待支付
    order = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert order["status"] == "pending"
    assert [t["status"] for t in order["timeline"]] == ["pending", "paid", "generating", "delivered"]
    assert order["canRefund"] is False

    # 回调置已支付（首次）
    cb = (await client.post(f"/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})).json()["data"]
    assert cb["status"] == "paid"
    assert cb["duplicated"] is False

    # 重复回调不重复发货
    cb2 = (await client.post(f"/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})).json()["data"]
    assert cb2["duplicated"] is True

    order = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert order["status"] == "paid"
    assert order["paidAt"]
    assert order["canRefund"] is True
    assert order["timeline"][1]["done"] is True

    # 付费后解锁锁定商机详情（M3-07 → M5 闭环）
    detail = (await client.get(f"/api/match/{locked_id}")).json()
    assert detail["code"] == 0, detail


async def test_callback_channel_mismatch_rejected(client, drain):
    _, _, created = await _prepared_order(client, drain, platform="web")
    body = (
        await client.post(
            "/api/payment/callback/wechat",
            json={"order_id": created["orderId"], "result": "success"},
        )
    ).json()
    assert body["code"] == 60001


async def test_refund_within_7_days_and_duplicate_rejected(client, drain):
    _, _, created = await _prepared_order(client, drain)
    order_id = created["orderId"]
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})

    refund = (
        await client.post("/api/payment/refund", json={"order_id": order_id, "reason": "不需要了"})
    ).json()
    assert refund["code"] == 0, refund
    assert refund["data"]["status"] == "refunded"
    assert "24 小时" in refund["data"]["message"]

    dup = (
        await client.post("/api/payment/refund", json={"order_id": order_id})
    ).json()
    assert dup["code"] == 40301


async def test_refund_before_payment_rejected(client, drain):
    _, _, created = await _prepared_order(client, drain)
    body = (
        await client.post("/api/payment/refund", json={"order_id": created["orderId"]})
    ).json()
    assert body["code"] == 60001


async def test_membership_grants_entitlement(client, drain):
    _, locked_id, created = await _prepared_order(client, drain, plan="year")
    order_id = created["orderId"]
    assert created["amountCents"] == 59900
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})
    # 年度会员：无需绑定单一商机即可查看锁定商机详情
    detail = (await client.get(f"/api/match/{locked_id}")).json()
    assert detail["code"] == 0, detail


async def test_idempotency_key_returns_same_order(client, drain):
    payload = {
        "plan": "month",
        "platform": "web",
        "matchId": None,
        "idempotencyKey": "key-abc-123",
    }
    first = (await client.post("/api/payment/create", json=payload)).json()["data"]
    second = (await client.post("/api/payment/create", json=payload)).json()["data"]
    assert first["orderId"] == second["orderId"]
    assert second["reused"] is True


async def test_unknown_order_returns_40401(client):
    body = (await client.get("/api/payment/order/no-such-order")).json()
    assert body["code"] == 40401


async def test_invalid_plan_rejected(client):
    body = (
        await client.post("/api/payment/create", json={"plan": "lifetime", "platform": "web"})
    ).json()
    assert body["code"] in (40001,)
