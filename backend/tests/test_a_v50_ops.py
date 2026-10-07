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


async def _new_order(client, login, plan="single") -> str:
    """只创建订单（不支付），返回 orderId。M0-01：下单前必须登录。"""
    await login(client)
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
async def test_query_order_recovers_when_callback_lost(client, drain, login):
    """回调丢失（渠道已扣款、本地仍待支付）时，主动查单必须补单，不能让用户白付钱。"""
    from app.services import payment as payment_service

    order_id = await _new_order(client, login)
    before = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert before["status"] == "pending"

    # 渠道侧已扣款，但回调丢了：本地订单仍是待支付
    await payment_service.mark_mock_channel_paid(order_id)

    # 主动查单 → 发现渠道已付 → 自动补单（用户无感）
    recovered = (await client.get(f"/api/payment/order/{order_id}")).json()["data"]
    assert recovered["status"] in ("paid", "generating", "delivered"), recovered
    assert recovered["paidAt"], recovered


# ---------------------------------------------------------------- M2-04 回调缺失告警
async def test_callback_missing_raises_admin_alert(client, _tables, login):
    """待支付订单长时间收不到渠道回调 → 生成后台告警，交人工核对（不静默丢单）。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import AdminAlert, Order
    from app.services import automation

    order_id = await _new_order(client, login)

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
async def test_admin_can_resolve_abnormal_order(client, _tables, login):
    """后台一键「标记已处理」：不再是异常高亮，且关联告警被关闭、动作可追溯。"""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Order
    from app.services import automation

    order_id = await _new_order(client, login)
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


# ════════════════════════════════════════════════════════════════════
#  第三轮核查补齐（M0-01 付费前登录 / M2 后台订单能力 / M0-03 后台额度）
# ════════════════════════════════════════════════════════════════════

async def test_guest_cannot_create_order(client):
    """M0-01：免费诊断免登录，但**付款这一步**必须登录。

    否则游客付款后一登录就换成新账号，已购权益 / 订单全部丢失（真实客诉级问题）。
    """
    body = (
        await client.post("/api/payment/create", json={"plan": "single", "platform": "web"})
    ).json()
    assert body["code"] == 40101, body
    assert "登录" in body["message"]


async def test_guest_data_claimed_on_login(client, login):
    """M0-01：游客期间产生的收藏，登录后必须归到账号名下，不能一登录就没了。"""
    from app.models import Favorite

    task_id = (await client.post("/api/diagnose", json=CONDITIONS)).json()["data"]["taskId"]
    await client.get("/api/match", params={"taskId": task_id})
    opp_id = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]["free"][0]["id"]
    await client.post(f"/api/match/{opp_id}/favorite")

    guest_favs = (await client.get("/api/match/favorites")).json()["data"]
    assert any(i["id"] == opp_id for i in guest_favs["items"]), guest_favs

    await login(client)  # 就地登录（客户端仍带 X-Guest-Token → 触发归集）

    claimed = (await client.get("/api/match/favorites")).json()["data"]
    assert any(i["id"] == opp_id for i in claimed["items"]), claimed

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Favorite).where(Favorite.opportunity_id == opp_id))).scalars().all()
        assert not any(r.owner_key.startswith("guest:") for r in rows)


async def test_admin_manual_refund_without_user_request(client, login):
    """M2-03：后台可对**用户未申请**的订单主动退款（重复支付 / 客诉补偿）。"""
    order_id = await _new_order(client, login)
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})
    headers = await _admin_token(client)

    listed = (await client.get("/api/admin/orders", params={"keyword": order_id}, headers=headers)).json()["data"]
    row = next((o for o in listed["items"] if o["id"] == order_id), None)
    assert row is not None and row["refundRequested"] is False

    res = (
        await client.put(
            f"/api/admin/orders/{order_id}/refund",
            json={"action": "approve", "reason": "疑似重复支付，主动退款"},
            headers=headers,
        )
    ).json()
    assert res["code"] == 0, res
    assert res["data"]["status"] == "refunded"
    assert "主动退款" in res["data"]["message"]


async def test_reject_without_pending_review_is_blocked(client, login):
    """M2-05：没有待审核申请的订单不允许「驳回」（防止后台越权空操作）。"""
    order_id = await _new_order(client, login)
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})
    headers = await _admin_token(client)
    res = (
        await client.put(
            f"/api/admin/orders/{order_id}/refund",
            json={"action": "reject", "reason": "误操作"},
            headers=headers,
        )
    ).json()
    assert res["code"] == 40901, res


async def test_admin_resend_order_recovers_missing_callback(client, login):
    """M2-03：一键补单 —— 渠道已扣款但回调丢失时，后台可主动补单发货。"""
    from app.services import payment as payment_service

    order_id = await _new_order(client, login)
    await payment_service.mark_mock_channel_paid(order_id)  # 渠道已扣款，回调未到

    headers = await _admin_token(client)
    res = (await client.post(f"/api/admin/orders/{order_id}/resend", headers=headers)).json()
    assert res["code"] == 0, res
    assert res["data"]["status"] in ("paid", "generating", "delivered"), res


async def test_admin_resend_refuses_when_channel_not_paid(client, login):
    """M2-04：渠道未确认支付时绝不擅自发货（fail-safe）。"""
    order_id = await _new_order(client, login)
    headers = await _admin_token(client)
    res = (await client.post(f"/api/admin/orders/{order_id}/resend", headers=headers)).json()
    assert res["code"] == 0, res
    assert res["data"]["delivered"] is False
    assert "未查询到" in res["data"]["message"] or "无需补单" in res["data"]["message"]


async def test_duplicate_payment_flagged_and_batch_resolved(client, login):
    """M2-04：重复支付必须能在后台标红，且「一键处理异常」要真的批量处理。"""
    await login(client)
    first = (await client.post("/api/payment/create", json={"plan": "month", "platform": "web"})).json()["data"]["orderId"]
    second = (await client.post("/api/payment/create", json={"plan": "year", "platform": "web"})).json()["data"]["orderId"]
    for oid in (first, second):
        await client.post("/api/payment/callback/alipay", json={"order_id": oid, "result": "success"})

    headers = await _admin_token(client)
    listed = (await client.get("/api/admin/orders", params={"pageSize": 100}, headers=headers)).json()["data"]
    drows = {o["id"]: o for o in listed["items"]}
    assert drows[first]["abnormal"] is True, drows.get(first)
    assert drows[first]["abnormalType"] == "duplicate_payment", drows.get(first)
    assert drows[second]["abnormalType"] == "duplicate_payment", drows.get(second)

    batch = (await client.post("/api/admin/orders/resolve-abnormal", json={"note": "批量核对"}, headers=headers)).json()
    assert batch["code"] == 0 and batch["data"]["handled"] >= 2, batch

    after = (await client.get("/api/admin/orders", params={"keyword": first}, headers=headers)).json()["data"]
    row = next((o for o in after["items"] if o["id"] == first), None)
    assert row["abnormal"] is False and row["abnormalHandled"] is True, row


async def test_admin_user_detail_exposes_member_quota(client, login):
    """M0-03：后台必须能查到会员到期剩余天数 / 已购次数 / 已用启动包数 / 额度剩余。"""
    from app.core.security import ACCESS_TOKEN_TYPE, decode_token

    token = await login(client)
    uid = decode_token(token, ACCESS_TOKEN_TYPE)
    order_id = (
        await client.post("/api/payment/create", json={"plan": "single", "platform": "web"})
    ).json()["data"]["orderId"]
    await client.post("/api/payment/callback/alipay", json={"order_id": order_id, "result": "success"})

    headers = await _admin_token(client)
    users = (await client.get("/api/admin/users", params={"pageSize": 100}, headers=headers)).json()["data"]
    row = next((u for u in users["items"] if u["id"] == uid), None)
    assert row is not None, "新建用户应出现在后台用户列表"
    for key in ("expireAt", "expireDaysLeft", "purchasedCount", "usedPackageCount",
                "quotaTotal", "quotaRemaining", "quotaUnlimited"):
        assert key in row, f"后台用户列表缺字段 {key}"

    detail = (await client.get(f"/api/admin/users/{uid}", headers=headers)).json()["data"]
    u = detail["user"]
    assert "quotaRemaining" in u and "expireDaysLeft" in u, u
    assert u["purchasedCount"] >= 1, u
    assert detail["orders"], "详情应包含订单"
    for key in ("downloaded", "refundRequested", "abnormal"):
        assert key in detail["orders"][0], f"详情订单缺字段 {key}"


async def test_home_config_tiers_match_frontend(client):
    """M1-01：首屏档位接口必须与前端滑块一致（此前后端 2 档 / 前端 3 档，属于契约漂移）。"""
    data = (await client.get("/api/home/config")).json()["data"]
    assert [h["value"] for h in data["dailyHours"]] == [2, 4, 8], data["dailyHours"]
    assert len(data["capitals"]) == 4, data["capitals"]
    assert data["cityVersion"], data


async def test_diagnose_progress_uses_real_case_count(client, drain):
    """M1-02 / 第 1.1 节：进度文案里的案例数必须来自真实案例库，不允许虚假宣传。"""
    from app.data import opportunities as opp_data
    from app.services import diagnose as diagnose_service

    labels = [label for _, label in diagnose_service.STAGES]
    assert any(str(opp_data.CASE_COUNT) in label for label in labels), labels
    assert all("1247" not in label for label in labels), labels
