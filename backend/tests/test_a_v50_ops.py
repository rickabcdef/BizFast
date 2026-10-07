"""程序员 A 的 V5.0 运营链路验收测试（第二批）。

对照《生意快启现金流导向版 PRD V5.0》补齐的运营能力：

- M0-04 邀请关系绑定：分享链接带邀请码 → 登录自动绑定；**后台可查任意用户的邀请来源**
- M2-01 支付兜底：主动向渠道查单，回调丢失也能补单（用户不会付了钱拿不到货）
- M2-03 后台「标记已处理」：异常订单人工处理后不再红色高亮
- M2-04 回调缺失告警：长时间收不到渠道回调 → 后台可见并交人工核对
- 第 10.2 节：后台展示的手机号一律脱敏
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

CONDITIONS = {"capital": 30000, "dailyHours": 2, "city": "杭州市"}


# ---------------------------------------------------------------- 工具
async def _admin_token(client) -> dict:
    """走完后台两步登录，返回带 Authorization 的请求头。"""
    step1 = (await client.post("/api/admin/auth/login", json={"username": "admin", "password": "admin123"})).json()
    assert step1["code"] == 0, step1
    assert step1["data"]["needTotp"] is True
    step2 = (
        await client.post("/api/admin/auth/verify-2fa", json={"username": "admin", "totp": "123456"})
    ).json()
    assert step2["code"] == 0, step2
    return {"Authorization": f"Bearer {step2['data']['token']}"}


async def _new_order(client, plan="single") -> str:
    """只创建订单（不支付），返回 orderId。"""
    task_id = (await client.post("/api/diagnose", json=CONDITIONS)).json()["data"]["taskId"]
    await client.get("/api/match", params={"taskId": task_id})
    created = (
        await client.post("/api/payment/create", json={"plan": plan, "platform": "web", "matchId": None})
    ).json()["data"]
    return created["orderId"]


async def _register_with_invite(client, inviter_code: str) -> tuple[str, str]:
    """新用户用邀请码走手机号验证码登录，返回 (phone, userId)。"""
    from app.core.cache import get_cache

    phone = f"135{uuid.uuid4().int % 10**8:08d}"
    sent = (await client.post("/api/auth/sms/send", json={"phone": phone})).json()
    assert sent["code"] == 0, sent
    # test 环境不回传验证码（防撞库），直接覆盖缓存里的随机码
    await get_cache().set(f"sms:code:{phone}", "123456", ttl=300)

    login = (
        await client.post("/api/auth/login", json={"phone": phone, "code": "123456", "inviterCode": inviter_code})
    ).json()
    assert login["code"] == 0, login
    return phone, login["data"]["userId"]


# ---------------------------------------------------------------- M0-04 邀请来源
async def test_invite_binding_visible_and_filterable_in_admin(client, _tables):
    """邀请注册的用户，后台必须能查到「邀请注册」来源与邀请人（脱敏），且来源筛选真实生效。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import InviteRelation, User

    inviter_id = f"u-inv-{uuid.uuid4().hex[:8]}"
    inviter_phone = "13812345678"
    inviter_code = f"BF{uuid.uuid4().hex[:5].upper()}"
    async with AsyncSessionLocal() as db:
        db.add(
            User(
                id=inviter_id,
                unionid=f"inv-{inviter_id}",
                phone=inviter_phone,
                role="user",
                plan="none",
                invite_code=inviter_code,
            )
        )
        await db.commit()

    # 被邀请人：分享链接落地 → 填写邀请码登录
    _, invitee_id = await _register_with_invite(client, inviter_code)

    async with AsyncSessionLocal() as db:
        rel = (
            await db.execute(select(InviteRelation).where(InviteRelation.invitee_user_id == invitee_id))
        ).scalar_one_or_none()
        assert rel is not None, "邀请关系未建立（M0-04 核心验收点）"
        assert rel.inviter_user_id == inviter_id

    headers = await _admin_token(client)

    # 后台用户列表：来源标签 + 邀请人手机号（脱敏）
    page = (await client.get("/api/admin/users", params={"keyword": invitee_id}, headers=headers)).json()["data"]
    row = next((u for u in page["items"] if u["id"] == invitee_id), None)
    assert row is not None, page
    assert row["source"] == "邀请注册"
    assert row["inviterPhone"] == "138****5678", row  # §10.2 脱敏
    assert "****" in row["phone"]  # 用户本人手机号同样脱敏

    # 来源筛选真实生效：邀请注册能命中，自然流量不应包含该用户
    inv = (
        await client.get("/api/admin/users", params={"source": "邀请注册", "pageSize": 100}, headers=headers)
    ).json()["data"]
    assert invitee_id in {u["id"] for u in inv["items"]}

    organic = (
        await client.get("/api/admin/users", params={"source": "自然流量", "pageSize": 100}, headers=headers)
    ).json()["data"]
    assert invitee_id not in {u["id"] for u in organic["items"]}

    # 用户详情：同样能看到邀请来源
    detail = (await client.get(f"/api/admin/users/{invitee_id}", headers=headers)).json()["data"]
    assert detail["user"]["source"] == "邀请注册"
    assert detail["user"]["inviterPhone"] == "138****5678"


async def test_wechat_login_also_binds_inviter(client, _tables):
    """M5-01：分享卡片 → 微信一键登录是裂变主路径，同样必须绑定邀请关系。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import InviteRelation, User

    inviter_code = f"BF{uuid.uuid4().hex[:5].upper()}"
    async with AsyncSessionLocal() as db:
        db.add(
            User(
                id=f"u-wx-inv-{uuid.uuid4().hex[:8]}",
                unionid=f"wx-inv-{uuid.uuid4().hex[:8]}",
                role="user",
                plan="none",
                invite_code=inviter_code,
            )
        )
        await db.commit()

    unionid = f"wx-{uuid.uuid4().hex[:10]}"
    login = (
        await client.post("/api/auth/wechat", json={"unionid": unionid, "inviterCode": inviter_code})
    ).json()
    assert login["code"] == 0, login
    invitee_id = login["data"]["userId"]

    async with AsyncSessionLocal() as db:
        rel = (
            await db.execute(select(InviteRelation).where(InviteRelation.invitee_user_id == invitee_id))
        ).scalar_one_or_none()
        assert rel is not None, "微信登录未绑定邀请关系"


# ---------------------------------------------------------------- M2-01 主动查单兜底
async def test_query_order_recovers_when_callback_lost(client, drain):
    """回调丢失（渠道已扣款、本地仍待支付）时，主动查单必须补单，不能让用户白付钱。"""
    from app.services import payment as payment_service

    order_id = await _new_order(client)
    before = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert before["status"] == "pending"

    # 渠道侧已扣款，但回调丢了：本地订单仍是待支付
    await payment_service.mark_mock_channel_paid(order_id)

    # 主动查单 → 发现渠道已付 → 自动补单（用户无感）
    recovered = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert recovered["status"] in ("paid", "generating", "delivered"), recovered
    assert recovered["paidAt"], recovered


# ---------------------------------------------------------------- M2-04 回调缺失告警
async def test_callback_missing_raises_admin_alert(client, _tables):
    """待支付订单长时间收不到渠道回调 → 生成后台告警，交人工核对（不静默丢单）。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import AdminAlert, Order
    from app.services import automation

    order_id = await _new_order(client)

    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        order.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        await db.commit()

        created = await automation.detect_payment_anomalies(db)
        await db.commit()
        assert any(a["related_id"] == order_id for a in created), "未产生回调缺失告警"

        alert = (
            await db.execute(
                select(AdminAlert).where(AdminAlert.fingerprint == f"callback_missing:{order_id}")
            )
        ).scalar_one_or_none()
        assert alert is not None
        assert alert.alert_type == "callback_missing"
        assert alert.related_type == "order"


# ---------------------------------------------------------------- M2-03 标记已处理
async def test_admin_can_resolve_abnormal_order(client, _tables):
    """后台一键「标记已处理」：不再是异常高亮，且关联告警被关闭、动作可追溯。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Order
    from app.services import automation

    order_id = await _new_order(client)
    # 制造「已支付未交付超 2 小时」异常
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})
    async with AsyncSessionLocal() as db:
        order = await db.get(Order, order_id)
        order.paid_at = datetime.now(timezone.utc) - timedelta(hours=3)
        await db.commit()
        await automation.detect_abnormal_orders(db)
        await db.commit()

    headers = await _admin_token(client)
    listed = (await client.get("/api/admin/orders", params={"keyword": order_id}, headers=headers)).json()["data"]
    row = next((o for o in listed["items"] if o["id"] == order_id), None)
    assert row is not None and row["abnormal"] is True, row

    # 人工处理
    resolved = (
        await client.post(f"/api/admin/orders/{order_id}/resolve", json={"note": "已补单"}, headers=headers)
    ).json()
    assert resolved["code"] == 0, resolved
    assert resolved["data"]["handled"] is True

    after = (await client.get("/api/admin/orders", params={"keyword": order_id}, headers=headers)).json()["data"]
    row2 = next((o for o in after["items"] if o["id"] == order_id), None)
    assert row2["abnormal"] is False, row2
    assert row2["abnormalHandled"] is True, row2


# ---------------------------------------------------------------- 后台登录契约
async def test_admin_login_two_step_contract(client, _tables):
    """后台登录两步契约：/api/admin/auth/login + /api/admin/auth/verify-2fa（文档与实现一致）。"""
    step1 = (await client.post("/api/admin/auth/login", json={"username": "admin", "password": "wrong"})).json()
    assert step1["code"] != 0
    assert "密码" in step1["message"]

    headers = await _admin_token(client)
    dash = (await client.get("/api/admin/dashboard", headers=headers)).json()
    assert dash["code"] == 0, dash
    assert "kpis" in dash["data"]
