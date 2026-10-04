"""M5-09 优惠券 / 邀请码 · M5-08 自动续费 · M5-10 风控 测试（负责人 A）。

对应 PRD 验收：
- M5-09 优惠券不可叠加使用，规则在页面明示
- M5-08 月/年会员支持自动续费，续费前 3 天提醒，可一键取消（取消入口 ≤3 步）
- M5-10 同一设备/IP 异常行为触发人工审核
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create_order(client, **overrides):
    payload = {"plan": "single", "platform": "web"}
    payload.update(overrides)
    return await client.post("/api/payment/create", json=payload)


# ---------------------------------------------------------------- M5-09 优惠券
async def test_coupon_validate_preview_and_rules_are_explicit(client):
    r = await client.post("/api/payment/coupon/validate", json={"code": "welcome5", "plan": "single"})
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    # 大小写不敏感
    assert data["code"] == "WELCOME5"
    assert data["discountCents"] == 500
    assert data["finalCents"] == 990 - 500
    # 金额文案统一由后端出（前端不重复实现四舍五入），三个标签必须自洽
    assert data["originalLabel"] == "9.9"
    assert data["discountLabel"] == "5"
    assert data["finalLabel"] == "4.9"
    # PRD：规则必须在页面明示 → 接口必须回传规则文案
    assert "不可叠加" in data["rules"]


async def test_coupon_preview_matches_actual_order_amount(client):
    """预览价必须等于真实下单后的实付金额，否则用户会觉得被「临时加价」。"""
    preview = (
        await client.post("/api/payment/coupon/validate", json={"code": "WELCOME5", "plan": "single"})
    ).json()["data"]
    created = (await _create_order(client, couponCode="WELCOME5")).json()["data"]
    assert created["amountCents"] == preview["finalCents"]
    assert created["amountLabel"] == preview["finalLabel"]
    assert created["originalLabel"] == preview["originalLabel"]
    assert created["discountLabel"] == preview["discountLabel"]


async def test_coupon_applied_to_order_and_not_stackable(client):
    """下单带券 → 实付金额 = 原价 - 减免；同一订单不可能再叠加第二张券。"""
    created = (await _create_order(client, couponCode="WELCOME5")).json()["data"]
    assert created["originalCents"] == 990
    assert created["discountCents"] == 500
    assert created["amountCents"] == 490
    assert created["couponCode"] == "WELCOME5"

    order = (await client.get(f"/api/payment/order/{created['orderId']}")).json()["data"]
    assert order["amountCents"] == 490
    assert order["discountCents"] == 500
    assert order["couponCode"] == "WELCOME5"


async def test_coupon_cannot_be_reused_by_same_account(client):
    """每个账号限用一次；第二次必须给中文原因，而不是静默失效。"""
    await _create_order(client, couponCode="WELCOME5", matchId="op_home_baking")
    second = (await _create_order(client, couponCode="WELCOME5", matchId="op_breakfast_cart")).json()
    assert second["code"] == 40301
    assert "用过" in second["message"]


async def test_coupon_plan_scope_and_min_amount_are_enforced(client):
    """年度专用券不能用在单次包上；不满足门槛要给出中文提示。"""
    r = (await client.post("/api/payment/coupon/validate", json={"code": "YEAR20", "plan": "single"})).json()
    assert r["code"] == 40301
    assert "年度会员" in r["message"]

    ok = (await client.post("/api/payment/coupon/validate", json={"code": "YEAR20", "plan": "year"})).json()["data"]
    assert ok["discountCents"] == 2000
    assert ok["finalCents"] == 19900 - 2000


async def test_invite_code_percent_discount(client):
    r = (await client.post("/api/payment/coupon/validate", json={"code": "invite10", "plan": "month"})).json()["data"]
    assert r["discountCents"] == round(3900 * 10 / 100)
    assert r["kind"] == "invite"


async def test_unknown_coupon_gives_chinese_message(client):
    r = (await client.post("/api/payment/coupon/validate", json={"code": "NOT-EXIST", "plan": "single"})).json()
    assert r["code"] == 40301
    assert r["message"] and any("\u4e00" <= ch <= "\u9fff" for ch in r["message"])


async def test_coupon_list_marks_usable_state(client):
    await _create_order(client, couponCode="WELCOME5")
    data = (await client.get("/api/payment/coupons")).json()["data"]
    by_code = {i["code"]: i for i in data["items"]}
    assert by_code["WELCOME5"]["usable"] is False
    assert by_code["WELCOME5"]["reason"] == "已使用过"
    assert "不可叠加" in data["rules"]


async def test_refund_releases_coupon_quota(client):
    """用券下单后退款，券额度必须归还，否则用户等于永久失去这张券。"""
    created = (await _create_order(client, couponCode="WELCOME5")).json()["data"]
    await client.post(f"/api/payment/callback/{created['channel']}", json={"order_id": created["orderId"]})
    refund = (await client.post("/api/payment/refund", json={"orderId": created["orderId"]})).json()
    assert refund["code"] == 0

    again = (await client.post("/api/payment/coupon/validate", json={"code": "WELCOME5", "plan": "single"})).json()
    assert again["code"] == 0, "退款后应能重新使用该券"


# ---------------------------------------------------------------- M5-08 自动续费
async def test_subscription_default_is_off_and_disclosed(client):
    data = (await client.get("/api/payment/subscription")).json()["data"]
    assert data["autoRenew"] is False
    assert data["renewable"] is False  # 非会员不适用
    assert "不会自动扣款" in data["notice"]


async def test_auto_renew_requires_membership(client):
    r = (await client.put("/api/payment/subscription", json={"autoRenew": True})).json()
    assert r["code"] == 40301
    assert "会员" in r["message"]


async def test_member_can_toggle_and_cancel_in_one_step(client):
    created = (await _create_order(client, plan="year", autoRenew=True)).json()["data"]
    await client.post(f"/api/payment/callback/{created['channel']}", json={"order_id": created["orderId"]})

    sub = (await client.get("/api/payment/subscription")).json()["data"]
    assert sub["isMember"] is True
    assert sub["plan"] == "year"
    assert sub["autoRenew"] is True
    assert sub["renewable"] is True
    assert sub["daysLeft"] is not None and sub["daysLeft"] > 360
    assert "3 天" in sub["notice"]

    # 一键取消（PRD：取消入口不超过 3 步，不允许设置取消障碍）
    canceled = (await client.post("/api/payment/subscription/cancel")).json()["data"]
    assert canceled["autoRenew"] is False
    assert "不再扣款" in canceled["message"]

    after = (await client.get("/api/payment/subscription")).json()["data"]
    assert after["autoRenew"] is False


async def test_member_can_opt_out_at_purchase_time(client):
    created = (await _create_order(client, plan="month", autoRenew=False)).json()["data"]
    await client.post(f"/api/payment/callback/{created['channel']}", json={"order_id": created["orderId"]})
    sub = (await client.get("/api/payment/subscription")).json()["data"]
    assert sub["plan"] == "month"
    assert sub["autoRenew"] is False


# ---------------------------------------------------------------- M5-10 风控
async def test_order_burst_triggers_manual_review(client):
    """同一账号 10 分钟内连续下单 ≥5 笔 → 命中刷单规则，标记人工审核而非静默拦截。"""
    last = None
    for i in range(6):
        last = (await _create_order(client, matchId=f"op_burst_{i}")).json()["data"]
    assert last["risk"]["flagged"] is True
    assert last["risk"]["signal"] == "order_burst"
    # 关键：仍然给出可读的中文说明，而不是「莫名被拦」
    assert "人工审核" in last["risk"]["notice"]

    overview = (await client.get("/api/payment/risk")).json()["data"]
    assert overview["hasReview"] is True
    assert any(i["signal"] == "order_burst" for i in overview["items"])


async def test_normal_usage_is_not_flagged(client):
    data = (await _create_order(client)).json()["data"]
    assert data["risk"]["flagged"] is False
    overview = (await client.get("/api/payment/risk")).json()["data"]
    assert overview["hasReview"] is False


async def test_risk_does_not_block_payment(client):
    """风控只做标记：命中后支付链路必须依然可用（避免误伤真实用户）。"""
    for i in range(6):
        created = (await _create_order(client, matchId=f"op_pay_{i}")).json()["data"]
    assert created["risk"]["flagged"] is True
    cb = (await client.post(f"/api/payment/callback/{created['channel']}", json={"order_id": created["orderId"]})).json()
    assert cb["code"] == 0
    assert cb["data"]["status"] == "paid"
