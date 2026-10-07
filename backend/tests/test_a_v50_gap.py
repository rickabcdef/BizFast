"""程序员 A 的 V5.0 查漏补缺验收测试。

对照《生意快启现金流导向版 PRD V5.0》A 的模块（M0 用户 / M1 诊断 / M2 支付订单）：

- M2-05 退款规则：交付物未下载前可自助全额退款；下载后退款需人工审核；退款后权益回收
- 第 2.3 节「今日限制」：真实计数的稀缺提示（数字来自真实订单，绝不造假）
- M0-02 用户画像：城市 / 资金区间 / 每日时间 / 经验，注册时自动采集
- M0-03 会员状态：已购次数 / 已用启动包数 / 额度剩余；到期前 3 天、1 天各提醒一次
- 第 10.2 节：敏感信息（手机号）脱敏展示
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

CONDITIONS = {"capital": 30000, "dailyHours": 2, "city": "杭州市"}


# ---------------------------------------------------------------- 工具
async def _paid_order(client, drain, plan="single"):
    """走完「诊断 → 商机 → 下单 → 支付成功」，返回 (taskId, matchId, orderId)。"""
    task_id = (await client.post("/api/diagnose", json=CONDITIONS)).json()["data"]["taskId"]
    await drain()
    match = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]
    locked_id = match["locked"]["id"]
    created = (
        await client.post(
            "/api/payment/create",
            json={"plan": plan, "platform": "web", "matchId": locked_id},
        )
    ).json()["data"]
    order_id = created["orderId"]
    await client.post(
        "/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"}
    )
    return task_id, locked_id, order_id


async def _wait_delivered(client, drain, order_id, tries=60):
    """等交付物生成完成（进程内队列 + 本地存储，通常 1—2 轮即可）。"""
    data = {}
    for _ in range(tries):
        await drain()
        data = (await client.get(f"/api/package/{order_id}")).json().get("data") or {}
        if data.get("status") in ("delivered", "failed"):
            return data
    return data


# ---------------------------------------------------------------- M2-05 退款规则（V5.0）
async def test_refund_before_download_is_self_service(client, drain):
    """未下载 → 自助全额退款即时生效，且不进入人工审核。"""
    _, _, order_id = await _paid_order(client, drain)

    order = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert order["downloaded"] is False
    assert order["refundPath"] == "self"
    assert order["canRefund"] is True
    assert "未下载" in order["refundNotice"]

    refund = (
        await client.post("/api/payment/refund", json={"order_id": order_id, "reason": "不需要了"})
    ).json()
    assert refund["code"] == 0, refund
    assert refund["data"]["status"] == "refunded"
    assert refund["data"]["review"] == "auto_approved"
    assert refund["data"]["reviewRequired"] is False


async def test_refund_after_download_needs_manual_review(client, drain):
    """已下载 → 退款不即时生效，转人工审核；后台订单列表可见该待审核申请。"""
    _, locked_id, order_id = await _paid_order(client, drain)

    created = (
        await client.post("/api/package/create", json={"orderId": order_id, "matchId": locked_id})
    ).json()
    assert created["code"] == 0, created
    pkg = await _wait_delivered(client, drain, order_id)
    assert pkg.get("status") == "delivered", pkg

    # 真实下载一件交付物（dl=1）；预览不带 dl，不算「已获取」
    resp = await client.get(f"/api/package/{order_id}/item/D01", params={"dl": 1})
    assert resp.status_code == 200, resp.text

    order = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert order["downloaded"] is True
    assert order["refundPath"] == "review"
    assert "人工审核" in order["refundNotice"]

    refund = (
        await client.post("/api/payment/refund", json={"order_id": order_id, "reason": "不合适"})
    ).json()
    assert refund["code"] == 0, refund
    assert refund["data"]["review"] == "pending"
    assert refund["data"]["reviewRequired"] is True
    # 关键：没有即时退款
    assert refund["data"]["status"] != "refunded"

    # 重复提交被拦（避免刷审核队列）
    dup = (await client.post("/api/payment/refund", json={"order_id": order_id})).json()
    assert dup["code"] == 40901

    # 已提交审核后不再允许再次自助退款
    order = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert order["refundReviewing"] is True
    assert order["canRefund"] is False


async def test_refund_revokes_membership_rights(client, drain):
    """V5.0 M2-05：退款后会员权益自动回收。"""
    from app.core.cache import get_cache
    from app.core.database import AsyncSessionLocal
    from app.models import User
    from sqlalchemy import select

    phone = f"138{uuid.uuid4().int % 10**8:08d}"
    await get_cache().set(f"sms:code:{phone}", "123456", ttl=300)
    login = (
        await client.post("/api/auth/login", json={"phone": phone, "code": "123456"})
    ).json()
    assert login["code"] == 0, login
    token = login["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = (
        await client.post("/api/diagnose", json=CONDITIONS)
    ).json()["data"]["taskId"]
    await drain()
    match = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]
    created = (
        await client.post(
            "/api/payment/create",
            json={"plan": "month", "platform": "web", "matchId": match["locked"]["id"]},
            headers=headers,
        )
    ).json()["data"]
    order_id = created["orderId"]
    await client.post(
        "/api/payment/callback/alipay",
        json={"order_id": order_id, "result": "success"},
        headers=headers,
    )

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.phone == phone))).scalar_one()
        assert user.plan == "month"
        uid = user.id

    refund = (
        await client.post(
            "/api/payment/refund", json={"order_id": order_id, "reason": "用不上"}, headers=headers
        )
    ).json()
    assert refund["code"] == 0, refund
    assert refund["data"]["rightsRevoked"] is True

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        assert user.plan == "none"
        assert user.plan_expire_at is None


# ---------------------------------------------------------------- 第 2.3 节「今日限制」
async def test_today_quota_is_real_and_grows_with_orders(client, drain):
    task_id = (await client.post("/api/diagnose", json=CONDITIONS)).json()["data"]["taskId"]
    await drain()
    match = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]
    free_id = match["free"][0]["id"]
    locked_id = match["locked"]["id"]

    # 计数口径 = 当天真实支付成功的订单数。同一次会话内多条用例共享同一个库，
    # 因此这里断言「增量」而不是绝对值（数字真实性用增量 +1 来证明）。
    before = (await client.get(f"/api/match/{locked_id}/today")).json()["data"]
    taken_before = before["todayTaken"]
    assert before["dailyLimit"] > 0
    assert before["todayRemaining"] == before["dailyLimit"] - taken_before
    assert f"{taken_before} 位用户" in before["notice"]
    assert before["soldOut"] is False

    # 免费商机详情里也带今日限制（详情底部提示）
    detail = (
        await client.get(f"/api/match/{free_id}", params={"taskId": task_id})
    ).json()["data"]
    assert detail["today"]["dailyLimit"] > 0
    assert "位用户" in detail["today"]["notice"]

    # 真付一单（明确绑定该商机）→ 计数 +1、剩余 -1，数字全部来自真实订单，不造假
    created = (
        await client.post(
            "/api/payment/create",
            json={"plan": "single", "platform": "web", "matchId": locked_id},
        )
    ).json()["data"]
    await client.post(
        "/api/payment/callback/alipay",
        json={"order_id": created["orderId"], "result": "success"},
    )

    after = (await client.get(f"/api/match/{locked_id}/today")).json()["data"]
    assert after["todayTaken"] == taken_before + 1
    assert after["todayRemaining"] == after["dailyLimit"] - after["todayTaken"]
    assert f"{after['todayTaken']} 位用户" in after["notice"]


# ---------------------------------------------------------------- M0-02 用户画像 + M0-03 额度
async def test_profile_captured_on_login_and_membership_quota(client, drain):
    from app.core.cache import get_cache

    # 游客先在首屏选条件并诊断（PRD：未登录可完成免费诊断）
    await client.post(
        "/api/diagnose",
        json={**CONDITIONS, "extra": {"experience": "some"}},
    )
    await drain()

    phone = f"139{uuid.uuid4().int % 10**8:08d}"
    await get_cache().set(f"sms:code:{phone}", "123456", ttl=300)
    login = (
        await client.post("/api/auth/login", json={"phone": phone, "code": "123456"})
    ).json()
    assert login["code"] == 0, login
    token = login["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # M0-02：注册时自动把首屏已选的条件落成用户画像（不重复问用户）
    # 城市与诊断链路同一套归一化：库里是「杭州」而不是「杭州市」
    me = (await client.get("/api/user/me", headers=headers)).json()["data"]
    assert me["city"] == "杭州"
    assert me["capitalBand"] == "3–10 万"
    assert me["dailyHoursBand"] == "2 小时以内"
    # 补充问答存的是 some 编码，画像对外必须落成中文文案（不能直接吐编码）
    assert me["experience"] == "有相关经验"

    # M0-03：额度字段齐全（未购买时为 0）
    assert me["purchasedCount"] == 0
    assert me["usedPackageCount"] == 0
    assert me["quotaRemaining"] == 0
    assert me["quotaUnlimited"] is False

    # 手动更新画像（≤6 个字段）
    updated = (
        await client.post(
            "/api/user/profile",
            json={"experience": "做过两年餐饮", "city": "上海市"},
            headers=headers,
        )
    ).json()["data"]
    assert updated["experience"] == "做过两年餐饮"
    assert updated["city"] == "上海"

    # 付费后额度随之变化：已购 1 次、可用 1 次
    created = (
        await client.post(
            "/api/payment/create",
            json={"plan": "single", "platform": "web", "matchId": None},
            headers=headers,
        )
    ).json()["data"]
    await client.post(
        "/api/payment/callback/alipay",
        json={"order_id": created["orderId"], "result": "success"},
        headers=headers,
    )
    me = (await client.get("/api/user/me", headers=headers)).json()["data"]
    assert me["purchasedCount"] == 1
    assert me["quotaRemaining"] == 1
    assert me["quotaUnlimited"] is False

    # 会员则不限量
    subscription = (await client.get("/api/payment/subscription", headers=headers)).json()["data"]
    assert "quotaRemaining" in subscription


async def test_renew_reminder_fires_at_3_and_1_days(_tables):
    """M0-03：到期前 3 天 / 1 天各提醒一次，且不要求已开启自动续费。"""
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models import Notification, User
    from app.services import payment as payment_service

    uid = f"u-{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        user = User(
            id=uid,
            role="user",
            plan="month",
            auto_renew=False,  # 关键：没开自动续费也要提醒
            plan_expire_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db.add(user)
        await db.commit()

        async def _count() -> int:
            return int(
                (
                    await db.execute(
                        select(func.count(Notification.id)).where(
                            Notification.owner_key == f"user:{uid}"
                        )
                    )
                ).scalar_one()
                or 0
            )

        # 第 1 档：到期前 3 天
        assert await payment_service.maybe_notify_renewal(db, user) is True
        assert await _count() == 1
        # 同档位不重复打扰
        assert await payment_service.maybe_notify_renewal(db, user) is False
        assert await _count() == 1

        # 第 2 档：推进到到期前 1 天 → 再提醒一次
        user.plan_expire_at = datetime.now(timezone.utc) + timedelta(hours=20)
        await db.commit()
        assert await payment_service.maybe_notify_renewal(db, user) is True
        assert await _count() == 2
        assert await payment_service.maybe_notify_renewal(db, user) is False


# ---------------------------------------------------------------- 第 10.2 节 敏感信息脱敏
async def test_admin_user_phone_is_masked(_tables):
    from app.core.database import AsyncSessionLocal
    from app.models import User
    from app.services import admin as admin_service

    phone = f"137{uuid.uuid4().int % 10**8:08d}"
    uid = f"u-{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        db.add(User(id=uid, phone=phone, role="user", plan="none"))
        await db.commit()

        data = await admin_service.get_users(db, page=1, page_size=100)
        row = next((i for i in data["items"] if i.id == uid), None)
        assert row is not None, "新建用户应在后台列表中出现"
        assert row.phone == f"{phone[:3]}****{phone[-4:]}"
        assert re.fullmatch(r"\d{3}\*{4}\d{4}", row.phone)


async def test_mask_phone_helper():
    from app.services.admin import _mask_phone

    assert _mask_phone("13812345678") == "138****5678"
    assert _mask_phone(None) == "未绑定"
    assert _mask_phone("") == "未绑定"
    assert _mask_phone("123") == "***"


async def test_frontend_city_options_are_all_supported():
    """M1-05 契约：前端城市选择器提供的每一项，后端城市库都必须认得。

    否则用户选中后会在 M2-01 校验被拦成 40002「城市暂不支持」——这是一个真实踩过的坑
    （前端曾提供「香港 / 澳门 / 台北市 / 高雄市」，后端库里根本没有这些条目）。
    """
    from pathlib import Path

    from app.data import cities as city_data

    ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "cities.ts"
    if not ts.exists():
        pytest.skip("前端城市常量文件不存在")
    text = ts.read_text(encoding="utf-8")
    block = re.search(r"export const CITIES: string\[\] = \[(.*?)\n\]", text, re.S)
    assert block, "未解析到前端 CITIES 列表"
    options = re.findall(r"'([^']+)'", block.group(1))
    assert len(options) >= 100, f"城市选项过少（{len(options)}），疑似解析失败"
    unsupported = [c for c in options if not city_data.is_supported(c)]
    assert unsupported == [], f"前端提供但后端不认得的城市：{unsupported}"
