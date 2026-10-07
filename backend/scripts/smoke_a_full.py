"""程序员 A 全链路端到端冒烟（V5.0）。

模拟一个真实用户从「进首屏」到「退款」的完整旅程，逐项验证 A 负责的
M0 用户与账号 / M1 商机诊断 / M2 支付与订单，以及运营后台侧的相关能力。

与 `tests/` 下的单元/接口测试互补：那份保证「每个点正确」，这份保证「一条链路走得通」。

用法：cd backend && python scripts/smoke_a_full.py
（脚本自带独立 SQLite 与本地存储，跑完自动清理，可反复执行）
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DB = "var/_smoke_a.db"
STORAGE = "var/_smoke_storage"

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{DB}"
os.environ["REDIS_URL"] = ""
os.environ["QUEUE_BACKEND"] = "inline"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = STORAGE
os.environ["PAYMENT_MOCK"] = "true"
os.environ["DIAGNOSE_STAGE_MIN_MS"] = "0"
os.environ["DIAGNOSE_MOCK_AI"] = "true"

for target in (BACKEND / DB, BACKEND / STORAGE):
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists():
        target.unlink()

import httpx  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.queue.runner import await_background  # noqa: E402

PASS, FAIL = [], []


def check(label: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    line = f"  [{mark}] {label}"
    if detail and not cond:
        line += f"  -> {detail}"
    print(line, flush=True)
    (PASS if cond else FAIL).append(label)


async def main() -> int:
    from app.core.database import AsyncSessionLocal
    from app.services import coupon as coupon_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        await coupon_service.seed_catalog(db)

    transport = httpx.ASGITransport(app=app)
    guest = f"smoke-guest-{uuid.uuid4().hex}"
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://smoke",
        headers={"X-Guest-Token": guest, "X-Forwarded-For": "10.77.1.1"},
        timeout=60,
    ) as c:
        # ══════════════ M1 商机诊断引擎 ══════════════
        print("\n== M1 商机诊断引擎 ==", flush=True)

        # M1-01 首屏点选式入口
        home = (await c.get("/api/home/config")).json()["data"]
        check(
            "M1-01 首屏配置：资金档位/时间档位/城市版本号齐全",
            bool(home.get("capitals")) and bool(home.get("dailyHours")) and "cityVersion" in home,
            str(home)[:180],
        )
        check(
            "M1-01 时间档位与前端滑块一致（兼职2h / 半天4h / 全职8h 三档）",
            [h["value"] for h in home["dailyHours"]] == [2, 4, 8],
            str(home["dailyHours"]),
        )

        # M1-02 三步极速诊断
        diag = (
            await c.post(
                "/api/diagnose",
                json={"capital": 30000, "dailyHours": 2, "city": "杭州市",
                      "extra": {"experience": "none"}},
            )
        ).json()
        check("M1-02 提交诊断返回 taskId", diag.get("code") == 0 and diag["data"].get("taskId"),
              str(diag)[:180])
        task_id = diag["data"]["taskId"]
        await await_background(60)

        prog = (await c.get(f"/api/diagnose/{task_id}/progress")).json()["data"]
        check("M1-02 进度接口返回阶段与百分比（真实进度）",
              "stage" in prog and "percent" in prog, str(prog)[:180])

        res = (await c.get(f"/api/diagnose/{task_id}/result")).json()["data"]
        check("M1-02 结果含标签", bool(res.get("tags")), str(res)[:180])

        # M1-04 机会热度图
        hm = await c.get(f"/api/diagnose/heatmap/{task_id}")
        check("M1-04 机会热度图可下载（PNG）",
              hm.status_code == 200 and hm.content[:8] == b"\x89PNG\r\n\x1a\n",
              f"{hm.status_code} {hm.headers.get('content-type')} {len(hm.content)}B")

        # M1-03 / M1-05 三个免费 + 第 4 个锁定
        match = (await c.get("/api/match", params={"taskId": task_id})).json()["data"]
        free = match.get("free") or []
        locked = match.get("locked") or {}
        check("M1-03 返回 3 个免费商机", len(free) == 3, f"free={len(free)}")
        check("M1-05 返回第 4 个锁定商机", bool(locked.get("id")), str(locked)[:180])
        first = free[0]
        fe = first.get("fiveElements") or {}
        mt = first.get("metrics") or {}
        check("M1-03 卡片含 5 个关键数字（资金/回本/毛利/首个客户/难度）",
              all(k in fe for k in ("capital", "payback", "margin", "firstCustomer", "difficulty")),
              str(fe)[:260])
        check("M1-03 卡片含结构化数字（回本月数/毛利率/难度星级）",
              all(k in mt for k in ("paybackMonths", "marginPercent", "difficultyStars")),
              str(mt)[:260])
        check("M1-03 卡片带风险点（诚实提示）", bool(first.get("risks")),
              str(first.get("risks"))[:160])

        free_detail = (
            await c.get(f"/api/match/{first['id']}", params={"taskId": task_id})
        ).json()["data"]
        check("M1-03 免费商机详情内嵌「今日限制」", "today" in free_detail)

        # M1-05 锁定商机未解锁 → 40301
        locked_resp = (
            await c.get(f"/api/match/{locked['id']}", params={"taskId": task_id})
        ).json()
        check("M1-05 锁定商机详情未解锁被拦（40301）",
              locked_resp.get("code") == 40301, str(locked_resp)[:180])

        # §2.3 今日限制（真实计数）
        today = (await c.get(f"/api/match/{locked['id']}/today")).json()["data"]
        check("§2.3 今日限制接口返回真实计数",
              all(k in today for k in ("todayTaken", "dailyLimit", "todayRemaining", "notice")),
              str(today)[:200])

        # ══════════════ M0 用户与账号体系 ══════════════
        print("\n== M0 用户与账号体系 ==", flush=True)

        from app.core.cache import get_cache

        phone = f"135{uuid.uuid4().int % 10**8:08d}"

        # M0-01（V5.0）：付费前**免登录**，所以游客期间的收藏不能因为登录而丢
        await c.post(f"/api/match/{locked['id']}/favorite")
        guest_favs = (await c.get("/api/match/favorites")).json()["data"]
        check("M0-01 游客可免登录收藏商机",
              any(f.get("id") == locked["id"] for f in (guest_favs.get("items") or [])),
              str(guest_favs)[:200])

        # M0-01 发送验证码
        sent = (await c.post("/api/auth/sms/send", json={"phone": phone})).json()
        check("M0-01 发送验证码", sent.get("code") == 0, str(sent)[:160])
        # test 环境不回传验证码（防泄露），按真实前端拿不到码的场景，注入一次
        await get_cache().set(f"sms:code:{phone}", "123456", ttl=300)

        login = (await c.post("/api/auth/login", json={"phone": phone, "code": "123456"})).json()
        check("M0-01 手机号验证码登录成功", login.get("code") == 0 and login["data"].get("token"),
              str(login)[:200])
        token = login["data"]["token"]
        h = {"Authorization": f"Bearer {token}"}

        # M0-01：登录成功后，游客期间的收藏必须归到账号名下（否则「一登录东西就没了」）
        claimed_favs = (await c.get("/api/match/favorites", headers=h)).json()["data"]
        check("M0-01 登录后游客收藏自动归到账号名下（不丢数据）",
              any(f.get("id") == locked["id"] for f in (claimed_favs.get("items") or [])),
              str(claimed_favs)[:200])

        # M0-01 微信授权登录（网页端占位 unionid）
        wx = (await c.post("/api/auth/wechat", json={"unionid": f"wx-{uuid.uuid4().hex[:10]}"})).json()
        check("M0-01 微信授权登录成功", wx.get("code") == 0 and wx["data"].get("token"),
              str(wx)[:200])

        # M0-02 用户画像采集
        me = (await c.get("/api/user/me", headers=h)).json()["data"]
        check("M0-02 登录后自动落画像：城市（与诊断同归一化）",
              me.get("city") == "杭州", str(me.get("city")))
        check("M0-02 画像：启动资金区间", bool(me.get("capitalBand")), str(me.get("capitalBand")))
        check("M0-02 画像：可投入时间区间", bool(me.get("dailyHoursBand")),
              str(me.get("dailyHoursBand")))
        check("M0-02 画像：经验（中文文案，不吐编码）",
              bool(me.get("experience")) and me["experience"] != "none",
              str(me.get("experience")))

        upd = (
            await c.post("/api/user/profile",
                         json={"experience": "做过两年餐饮", "city": "上海市"}, headers=h)
        ).json()
        check("M0-02 手动更新画像（≤6 字段、点选式）",
              upd.get("code") == 0 and upd["data"].get("experience") == "做过两年餐饮",
              str(upd)[:200])

        # M0-03 会员状态
        check("M0-03 额度字段齐全（已购/已用/总额度/剩余/不限量）",
              all(k in me for k in ("purchasedCount", "usedPackageCount", "quotaTotal",
                                    "quotaRemaining", "quotaUnlimited")),
              str(list(me.keys()))[:240])

        # M0-04 邀请关系绑定
        inviter_code = (await c.get("/api/user/me", headers=h)).json()["data"].get("inviteCode")
        phone2 = f"136{uuid.uuid4().int % 10**8:08d}"
        await get_cache().set(f"sms:code:{phone2}", "123456", ttl=300)
        login2 = (
            await c.post("/api/auth/login",
                         json={"phone": phone2, "code": "123456", "inviterCode": inviter_code})
        ).json()
        check("M0-04 新用户凭邀请码登录并自动绑定邀请人",
              login2.get("code") == 0, str(login2)[:200])
        h2 = {"Authorization": f"Bearer {login2['data']['token']}"}

        # ══════════════ M2 支付与订单 ══════════════
        print("\n== M2 支付与订单 ==", flush=True)

        # M0-01（V5.0）：免费诊断不拦登录，**付款这一步**必须要求登录
        guest_pay = (
            await c.post("/api/payment/create", json={"plan": "single", "platform": "web"})
        ).json()
        check("M0-01 游客下单被拦（提示先登录，40101）",
              guest_pay.get("code") == 40101 and "登录" in (guest_pay.get("message") or ""),
              str(guest_pay)[:200])

        # M2-02 三档支付入口
        plans = (await c.get("/api/payment/plans")).json()["data"]
        plan_list = plans if isinstance(plans, list) else plans.get("plans", [])
        prices = {p.get("plan") or p.get("key"): p.get("price") or p.get("amount") or p.get("priceYuan")
                  for p in plan_list}
        check("M2-02 三档定价为 29.9 / 99 / 599",
              _has_price(plan_list, 2990) and _has_price(plan_list, 9900) and _has_price(plan_list, 59900),
              str(plan_list)[:300])

        addons = (await c.get("/api/payment/addons")).json()["data"]
        check("V5.0 档位5 增值加购包可见", bool(addons), str(addons)[:200])

        # M2-01 微信支付下单
        created = (
            await c.post("/api/payment/create",
                         json={"plan": "single", "platform": "web", "matchId": locked["id"]},
                         headers=h)
        ).json()
        check("M2-01 创建支付订单并返回支付参数",
              created.get("code") == 0 and created["data"].get("orderId")
              and created["data"].get("payParams") is not None,
              str(created)[:240])
        order_id = created["data"]["orderId"]

        pending = (await c.get(f"/api/payment/order/{order_id}", headers=h)).json()["data"]
        check("M2-03 订单可查（待支付）", pending.get("status") == "pending",
              str(pending.get("status")))

        # M2-01 支付回调
        cb = (await c.post("/api/payment/callback/alipay",
                           json={"order_id": order_id, "result": "success"}, headers=h)).json()
        check("M2-01 支付回调成功发货", cb.get("code") == 0, str(cb)[:200])

        paid = (await c.get(f"/api/payment/order/{order_id}", headers=h)).json()["data"]
        check("M2-01 支付后订单转已支付", paid.get("status") in ("paid", "generating", "delivered"),
              str(paid.get("status")))

        # 主动查单兜底
        q = (await c.get(f"/api/payment/order/{order_id}", headers=h)).json()
        check("M2-01 主动查单兜底可用", q.get("code") == 0)

        # 付费后额度变化（M0-03）
        me2 = (await c.get("/api/user/me", headers=h)).json()["data"]
        check("M0-03 付费后已购次数 +1 且额度可见",
              me2.get("purchasedCount") == 1 and me2.get("quotaRemaining") >= 1,
              f"purchased={me2.get('purchasedCount')} remain={me2.get('quotaRemaining')}")

        # 解锁后锁定商机详情可见
        unlocked = (await c.get(f"/api/match/{locked['id']}", headers=h,
                                params={"taskId": task_id})).json()
        check("M1-05 付费后锁定商机详情解锁可见", unlocked.get("code") == 0,
              str(unlocked)[:160])

        # 今日限制随真实订单 +1
        today2 = (await c.get(f"/api/match/{locked['id']}/today")).json()["data"]
        check("§2.3 今日限制计数随真实付费 +1",
              today2["todayTaken"] == today["todayTaken"] + 1,
              f"{today['todayTaken']} -> {today2['todayTaken']}")

        # ══════════════ M2-05 退款：未下载自助全额退 ══════════════
        print("\n== M2-05 退款机制 ==", flush=True)

        before = (await c.get(f"/api/payment/order/{order_id}", headers=h)).json()["data"]
        check("M2-05 未下载订单退款路径 = 自助",
              before.get("refundPath") == "self" and before.get("downloaded") is False,
              f"path={before.get('refundPath')} downloaded={before.get('downloaded')}")

        rf = (await c.post("/api/payment/refund",
                           json={"order_id": order_id, "reason": "不需要了"}, headers=h)).json()
        check("M2-05 未下载 → 自助全额退款即时生效",
              rf.get("code") == 0 and rf["data"].get("status") == "refunded"
              and rf["data"].get("review") == "auto_approved",
              str(rf)[:240])

        me3 = (await c.get("/api/user/me", headers=h)).json()["data"]
        check("M2-05 退款后会员权益自动回收", me3.get("plan") in (None, "none"),
              str(me3.get("plan")))

        # ══════════════ M2-05 退款：已下载转人工审核 ══════════════
        created2 = (
            await c.post("/api/payment/create",
                         json={"plan": "single", "platform": "web", "matchId": locked["id"]},
                         headers=h)
        ).json()["data"]
        order2 = created2["orderId"]
        await c.post("/api/payment/callback/alipay",
                     json={"order_id": order2, "result": "success"}, headers=h)

        pkg = (await c.post("/api/package/create",
                            json={"orderId": order2, "matchId": locked["id"]},
                            headers=h)).json()
        check("M3 订单 → 启动包生成任务创建（订单联动）", pkg.get("code") == 0, str(pkg)[:200])

        pkg_data = {}
        for _ in range(60):
            await await_background(60)
            pkg_data = (await c.get(f"/api/package/{order2}", headers=h)).json().get("data") or {}
            if pkg_data.get("status") in ("delivered", "failed"):
                break
        check("M3 启动包生成完成且交付物齐全",
              pkg_data.get("status") == "delivered"
              and len(pkg_data.get("items") or []) == 10,
              f"status={pkg_data.get('status')} items={len(pkg_data.get('items') or [])}")

        dl = await c.get(f"/api/package/{order2}/item/D01", params={"dl": 1}, headers=h)
        check("M3 单件下载可用（dl=1 记已下载）", dl.status_code == 200,
              f"{dl.status_code} {len(dl.content)}B")

        after_dl = (await c.get(f"/api/payment/order/{order2}", headers=h)).json()["data"]
        check("M2-05 下载后订单标记为已下载、退款路径 = 人工审核",
              after_dl.get("downloaded") is True and after_dl.get("refundPath") == "review",
              f"downloaded={after_dl.get('downloaded')} path={after_dl.get('refundPath')}")

        rf2 = (await c.post("/api/payment/refund",
                            json={"order_id": order2, "reason": "不合适"}, headers=h)).json()
        check("M2-05 已下载 → 退款转人工审核（不即时退）",
              rf2.get("code") == 0 and rf2["data"].get("review") == "pending"
              and rf2["data"].get("reviewRequired") is True
              and rf2["data"].get("status") != "refunded",
              str(rf2)[:240])

        # ══════════════ M4 运营后台（A 相关的订单/用户/告警） ══════════════
        print("\n== M2-03 / M2-04 运营后台 ==", flush=True)

        step1 = (await c.post("/api/admin/auth/login",
                              json={"username": "admin", "password": "admin123"})).json()
        check("M2-03 后台登录第一步（账号密码）", step1.get("code") == 0,
              str(step1)[:200])
        step2 = (await c.post("/api/admin/auth/verify-2fa",
                              json={"username": "admin", "totp": "123456"})).json()
        check("M2-03 后台登录第二步（二次验证）签发会话",
              step2.get("code") == 0 and bool((step2.get("data") or {}).get("token")),
              str(step2)[:200])
        ah = {"Authorization": f"Bearer {step2['data']['token']}"}

        dash = (await c.get("/api/admin/dashboard", headers=ah)).json()
        check("M2-03 后台看板可打开", dash.get("code") == 0, str(dash)[:160])

        orders = (await c.get("/api/admin/orders", headers=ah)).json()["data"]
        items = orders.get("items") if isinstance(orders, dict) else orders
        items = items or []
        row = next((o for o in items if o.get("id") == order2), None)
        check("M2-03 后台订单列表可查所有订单", row is not None, f"共 {len(items)} 单")
        if row:
            check("M2-05 后台可见退款待审核 + 已下载标记",
                  row.get("refundRequested") is True and row.get("downloaded") is True,
                  f"refundRequested={row.get('refundRequested')} downloaded={row.get('downloaded')}")

        users = (await c.get("/api/admin/users", headers=ah)).json()["data"]
        uitems = users.get("items") if isinstance(users, dict) else users
        uitems = uitems or []
        target_uid = login["data"].get("userId") or login["data"].get("user_id")
        masked = next((u for u in uitems if u.get("id") == target_uid), None)
        if masked is None:
            masked = next((u for u in uitems if "****" in (u.get("phone") or "")), None)
        check("§10.2 后台用户列表手机号已脱敏",
              masked is not None and "****" in (masked.get("phone") or ""),
              str(masked.get("phone") if masked else None))

        alerts = (await c.get("/api/admin/alerts", headers=ah)).json()
        check("M2-04 后台告警接口可用", alerts.get("code") == 0, str(alerts)[:160])

        scan = (await c.post("/api/admin/alerts/scan", headers=ah)).json()
        check("M2-04 异常订单一键巡检可用", scan.get("code") == 0, str(scan)[:160])

        # 后台同意退款 → 权益回收
        if row:
            ok_refund = (await c.put(f"/api/admin/orders/{order2}/refund",
                                     json={"action": "approve", "reason": "核实无误"},
                                     headers=ah)).json()
            check("M2-05 后台一键同意退款（走权益回收链路）",
                  ok_refund.get("code") == 0, str(ok_refund)[:200])
            final = (await c.get(f"/api/payment/order/{order2}", headers=h)).json()["data"]
            check("M2-05 审核通过后订单转已退款", final.get("status") == "refunded",
                  str(final.get("status")))

        # ══════════════ V5.0 本轮补齐的运营链路 ══════════════
        print("\n== V5.0 运营链路（本轮补齐） ==", flush=True)

        from app.models import Order as _Order
        from app.services import automation as automation_service
        from app.services import payment as payment_service

        # M0-04：后台可查任意用户的邀请来源 + 来源筛选真实生效（此前筛选参数是摆设）
        invitee_id = login2["data"]["userId"]
        invitee = next((u for u in uitems if u.get("id") == invitee_id), None)
        check("M0-04 后台显示「邀请注册」来源 + 邀请人（已脱敏）",
              invitee is not None and invitee.get("source") == "邀请注册"
              and "****" in (invitee.get("inviterPhone") or ""),
              str(invitee)[:240] if invitee else "列表中未找到被邀请人")
        filtered = (await c.get("/api/admin/users",
                                params={"source": "邀请注册", "pageSize": 100},
                                headers=ah)).json()["data"]
        check("M0-04 后台按来源筛选真实生效",
              any(u.get("id") == invitee_id for u in (filtered.get("items") or [])),
              f"命中 {len(filtered.get('items') or [])} 人")

        # M2-01：回调丢失（渠道已扣款、本地仍待支付）→ 主动查单自动补单
        task3 = (await c.post("/api/diagnose",
                              json={"capital": 30000, "dailyHours": 2, "city": "杭州市",
                                    "extra": {"experience": "none"}})).json()["data"]["taskId"]
        await await_background()
        m3 = (await c.get("/api/match", params={"taskId": task3})).json()["data"]
        order3 = (await c.post("/api/payment/create",
                               json={"plan": "single", "platform": "web",
                                     "matchId": m3["locked"]["id"]},
                               headers=h)).json()["data"]["orderId"]
        await payment_service.mark_mock_channel_paid(order3)  # 渠道已扣款，回调丢了
        before3 = (await c.get(f"/api/payment/order/{order3}", headers=h)).json()["data"]
        after3 = (await c.get(f"/api/payment/order/{order3}", headers=h)).json()["data"]
        check("M2-01 回调丢失时主动查单自动补单",
              after3.get("status") in ("paid", "generating", "delivered")
              and bool(after3.get("paidAt")),
              f"前={before3.get('status')} 后={after3.get('status')}")

        # M2-04 / M2-03：回调缺失告警 → 后台标红 → 一键标记已处理
        # 注意用月卡下单：单次卡对「同用户 + 同商机」会幂等复用已存在的订单，测不出独立订单
        order4 = (await c.post("/api/payment/create",
                               json={"plan": "month", "platform": "web"},
                               headers=h)).json()["data"]["orderId"]
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        async with AsyncSessionLocal() as db:
            o4 = await db.get(_Order, order4)
            o4.created_at = _dt.now(_tz.utc) - _td(minutes=20)  # 超过回调缺失阈值（15 分钟）
            await db.commit()
            await automation_service.detect_payment_anomalies(db)
            await db.commit()

        oc = (await c.get("/api/admin/orders", params={"keyword": order4},
                          headers=ah)).json()["data"]
        ocrow = next((o for o in (oc.get("items") or []) if o.get("id") == order4), None)
        check("M2-04 回调缺失订单在后台标红可见",
              ocrow is not None and ocrow.get("abnormal") is True
              and ocrow.get("abnormalType") == "callback_missing",
              str(ocrow)[:240] if ocrow else "未找到订单")
        resolved = (await c.post(f"/api/admin/orders/{order4}/resolve",
                                 json={"note": "已人工核对并补单"}, headers=ah)).json()
        check("M2-03 后台一键标记已处理", resolved.get("code") == 0, str(resolved)[:200])
        oc2 = (await c.get("/api/admin/orders", params={"keyword": order4},
                           headers=ah)).json()["data"]
        ocrow2 = next((o for o in (oc2.get("items") or []) if o.get("id") == order4), None)
        check("M2-03 标记后不再红色高亮（异常清零）",
              ocrow2 is not None and ocrow2.get("abnormal") is False
              and ocrow2.get("abnormalHandled") is True,
              str(ocrow2)[:240] if ocrow2 else "未找到订单")

        # ══════════════ 第三轮核查补齐的能力 ══════════════
        print("\n== 第三轮核查补齐（重复支付 / 一键处理 / 补单 / 主动退款 / 后台额度） ==", flush=True)

        # M2-04：同一用户短窗口内两笔已支付 → 疑似重复支付，两条都必须标红
        dup_a = (
            await c.post("/api/payment/create", json={"plan": "month", "platform": "web"}, headers=h)
        ).json()["data"]["orderId"]
        dup_b = (
            await c.post("/api/payment/create", json={"plan": "year", "platform": "web"}, headers=h)
        ).json()["data"]["orderId"]
        for oid in (dup_a, dup_b):
            await c.post("/api/payment/callback/alipay",
                         json={"order_id": oid, "result": "success"}, headers=h)

        dl = (await c.get("/api/admin/orders", params={"pageSize": 100}, headers=ah)).json()["data"]
        drows = {o["id"]: o for o in (dl.get("items") or [])}
        check("M2-04 疑似重复支付在后台标红（此前该类型从不产出）",
              drows.get(dup_a, {}).get("abnormalType") == "duplicate_payment"
              and drows.get(dup_b, {}).get("abnormalType") == "duplicate_payment",
              f"{drows.get(dup_a, {}).get('abnormalType')} / {drows.get(dup_b, {}).get('abnormalType')}")

        # M2-04：一键处理异常必须**真的处理**（此前只是把列表切到「仅异常」筛选）
        rb = (await c.post("/api/admin/orders/resolve-abnormal",
                           json={"note": "批量核对完成"}, headers=ah)).json()
        check("M2-04 一键处理异常真实批量处理（不再只是切换筛选）",
              rb.get("code") == 0 and rb["data"].get("handled", 0) >= 1,
              str(rb)[:220])

        d_after = (await c.get("/api/admin/orders", params={"keyword": dup_a}, headers=ah)).json()["data"]
        da = next((o for o in (d_after.get("items") or []) if o["id"] == dup_a), None)
        check("M2-04 批量处理后重复支付不再标红",
              da is not None and da.get("abnormal") is False and da.get("abnormalHandled") is True,
              str(da)[:220])

        # M2-03：后台**主动退款**（用户没申请也能退，走完整权益回收链路）
        mref = (await c.put(f"/api/admin/orders/{dup_b}/refund",
                            json={"action": "approve", "reason": "疑似重复支付，主动退款"},
                            headers=ah)).json()
        check("M2-03 后台主动退款（用户未申请 → 支持手动退款）",
              mref.get("code") == 0 and mref["data"].get("status") == "refunded",
              str(mref)[:220])

        # M2-03：一键补单 —— 渠道已扣款但回调丢失
        task_r = (await c.post("/api/diagnose",
                               json={"capital": 30000, "dailyHours": 2, "city": "杭州市",
                                     "extra": {"experience": "none"}})).json()["data"]["taskId"]
        await await_background()
        order_r = (await c.post("/api/payment/create",
                                json={"plan": "month", "platform": "web"},
                                headers=h)).json()["data"]["orderId"]
        await payment_service.mark_mock_channel_paid(order_r)  # 渠道已扣款，回调丢了
        rs = (await c.post(f"/api/admin/orders/{order_r}/resend", headers=ah)).json()
        check("M2-03 后台一键补单（渠道已扣款 → 补单成功）",
              rs.get("code") == 0
              and rs["data"].get("status") in ("paid", "generating", "delivered"),
              str(rs)[:220])

        # M0-03：后台用户详情必须能查到会员到期/已购/已用/额度剩余
        det = (await c.get(f"/api/admin/users/{target_uid}", headers=ah)).json()["data"]
        u = det.get("user") or {}
        check("M0-03 后台用户详情含会员到期 / 已购次数 / 已用启动包 / 额度剩余",
              all(k in u for k in ("expireAt", "expireDaysLeft", "purchasedCount",
                                   "usedPackageCount", "quotaTotal", "quotaRemaining",
                                   "quotaUnlimited")),
              str({k: u.get(k) for k in ("expireAt", "expireDaysLeft", "purchasedCount",
                                         "usedPackageCount", "quotaRemaining", "quotaUnlimited")}))
        d_orders = det.get("orders") or []
        check("M0-03 后台用户详情订单含真实「已下载 / 退款申请 / 异常」字段",
              bool(d_orders) and all(k in d_orders[0] for k in ("downloaded", "refundRequested", "abnormal")),
              str(d_orders[0])[:220] if d_orders else "无订单")

        # M2-05：驳回一个「没有待审核申请」的订单必须被拦（越权空操作防护）
        bad_reject = (await c.put(f"/api/admin/orders/{order_r}/refund",
                                  json={"action": "reject", "reason": "误操作"}, headers=ah)).json()
        check("M2-05 驳回无待审核申请的订单被拦（40901）",
              bad_reject.get("code") == 40901, str(bad_reject)[:200])

        # M1-03：免费卡片必须带「核心风险点」（此前只在付费详情页才有）
        free_risks = [bool(card.get("risks")) for card in free]
        check("M1-03 三张免费卡片全部带风险点（前端卡片可渲染）",
              all(free_risks), f"risks 齐备情况={free_risks}")

    await engine.dispose()
    print(f"\n===== 冒烟结果：{len(PASS)} 通过 / {len(FAIL)} 失败 =====", flush=True)
    if FAIL:
        print("失败项：", flush=True)
        for f in FAIL:
            print(f"  - {f}", flush=True)
    return 1 if FAIL else 0


def _has_price(plan_list, cents: int) -> bool:
    for p in plan_list:
        for k in ("priceCents", "price_cents", "price", "amount", "amountCents", "amount_cents"):
            if p.get(k) == cents:
                return True
        for k in ("priceYuan", "price_yuan", "priceLabel", "price_label", "label", "amountLabel"):
            v = str(p.get(k) or "")
            if f"{cents / 100:g}" in v:
                return True
    return False


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
