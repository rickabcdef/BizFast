"""M2 付费与订单 业务逻辑层 - 负责人 A

- M2-02 三档支付入口（V5.0）：开业礼包 29.9 单次 / AI 合伙人月卡 99 / 创业陪跑年卡 599
  另附档位 5「增值加购包」（按项计价，绝不并入标准套餐）
- M5-04 支付渠道适配：按端选择渠道（Web 走支付宝/微信，小程序走微信 JSAPI，iOS 走 IAP…）
- M5-05 订单状态机：待支付 → 已支付 → 生成中 → 已交付；→ 已关闭；已支付/生成中/已交付 → 已退款
- M5-06 支付回调 + 主动查单双保险，不存在漏单
- M2-05 退款机制（V5.0）：交付物**未下载**可自助全额退款并即时回收权益；
  已下载的退款申请转人工审核（后台一键同意 / 驳回），审核通过后同样回收权益
- 幂等：同一 Idempotency-Key / 同一用户同一商机的重复创建返回既有订单

未接真实渠道时（PAYMENT_MOCK=true）走本地模拟支付，用于本地联调与验收；
真实渠道只需在 handle_callback 中补签名校验与网关调用，状态机无需改动。

V5.0 心理账户命名（第 2.1 节）：付费名称永远不叫「会员费」，叫「开业礼包」「AI 合伙人」「创业陪跑」。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.context import OwnerContext, ensure_owner_user
from app.core.errors import BizError
from app.models import Order, PaymentRecord
from app.services import coupon as coupon_service
from app.services import notify as notify_service
from app.services import risk as risk_service
from app.services.money import amount_label

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "generating": "生成中",
    "delivered": "已交付",
    "refunded": "已退款",
    "closed": "已关闭",
}

# V5.0 心理账户命名（第 2.1 节）
PLAN_NAMES = {"single": "开业礼包", "month": "AI 合伙人月卡", "year": "创业全程陪跑年卡"}
PLAN_UNITS = {"single": "单次", "month": "每月", "year": "每年"}

# V5.0 档位 5：增值加购包（第 2.2 节；成本 ≤ 售价 20%，绝不并进标准套餐）
ADDON_NAMES = {
    "poster": "AI 海报加印",
    "video": "AI 短视频",
    "avatar": "数字人口播",
    "leads": "供应商深度线索包",
    "logo": "AI Logo 与 VI",
}
ADDON_UNITS = {
    "poster": "张",
    "video": "条",
    "avatar": "条",
    "leads": "套",
    "logo": "套",
}

# 状态机允许的流转（M5-05）
TRANSITIONS = {
    "pending": {"paid", "closed"},
    "paid": {"generating", "refunded", "closed"},
    "generating": {"delivered", "refunded"},
    "delivered": {"refunded"},
    "refunded": set(),
    "closed": set(),
}

TIMELINE_STEPS = ["pending", "paid", "generating", "delivered"]

# 「进行中」的订单状态：同一用户 + 同一商机只会有一份进行中的订单
ACTIVE_STATUSES = ("pending", "paid", "generating", "delivered")


def plan_price(plan: str) -> int:
    return {
        "single": settings.price_single_cents,
        "month": settings.price_month_cents,
        "year": settings.price_year_cents,
    }.get(plan, 0)


def plan_options() -> list[dict]:
    """V5.0 M2-02：三档支付入口同屏展示，单次（开业礼包）高亮为主推档。"""
    return [
        {
            "plan": "single",
            "name": PLAN_NAMES["single"],
            "price_cents": settings.price_single_cents,
            "price_label": amount_label(settings.price_single_cents),
            "unit_label": "单次",
            "highlight": True,
            "badge": "★ 现金流主力",
            "rights": [
                "10 件完整启动包交付物",
                "2 个零风险小工具使用权 30 天",
                "永久保存在账号下，可随时重新下载",
            ],
        },
        {
            "plan": "month",
            "name": PLAN_NAMES["month"],
            "price_cents": settings.price_month_cents,
            "price_label": amount_label(settings.price_month_cents),
            "unit_label": "每月",
            "highlight": False,
            "badge": "月度经常性收入",
            "rights": [
                "无限次生成启动包",
                "AI 生意教练 7×24 对话",
                "工具箱全部功能",
                "每周商机库更新",
            ],
        },
        {
            "plan": "year",
            "name": PLAN_NAMES["year"],
            "price_cents": settings.price_year_cents,
            "price_label": amount_label(settings.price_year_cents),
            "unit_label": "每年",
            "highlight": False,
            "badge": "拉高 LTV",
            "rights": [
                "月卡全部权益",
                "30 天深度陪跑（每日任务 / 场景模拟 / 每周复盘）",
                f"{settings.year_gift_video_quota} 条 AI 短视频 + {settings.year_gift_avatar_quota} 条数字人口播体验额度",
                "折合每月约 " + amount_label(round(settings.price_year_cents / 12)),
            ],
        },
    ]


def addon_options() -> list[dict]:
    """V5.0 档位 5：增值加购包（按项计价，绝不并入标准套餐）。

    成本红线（第 7.3）：AI 视频 49/条、数字人口播 99/条，加购毛利率 ≥ 80%；
    标准套餐（单次/月卡/年卡）不包含任何 AI 生成视频与数字人。
    """
    prices = settings.addon_prices_cents or {}
    return [
        {
            "addon": code,
            "name": ADDON_NAMES[code],
            "price_cents": int(prices.get(code, 0)),
            "price_label": amount_label(int(prices.get(code, 0))),
            "unit_label": ADDON_UNITS[code],
        }
        for code in ADDON_NAMES
        if code in prices
    ]


def addon_price(addon: str) -> int:
    return int((settings.addon_prices_cents or {}).get(addon, 0))


def gift_tool_days(plan: str) -> int:
    """开业礼包附赠工具箱使用权天数（V5.0 档位 2：2 个零风险小工具 30 天）。"""
    return settings.gift_tool_days if plan == "single" else 0


def pay_channel_for(platform: str) -> str:
    """M5-04：按端适配支付渠道。"""
    return {
        "weapp": "wechat",
        "ios": "apple",
        "harmony": "huawei",
        "android": "wechat",
        "web": "alipay",
        "win": "alipay",
        "mac": "alipay",
    }.get(platform, "alipay")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _record(db, order_id: str, channel: str, action: str, status: str, payload: dict | None = None) -> None:
    db.add(
        PaymentRecord(
            id=str(uuid.uuid4()),
            order_id=order_id,
            channel=channel,
            action=action,
            status=status,
            payload=json.dumps(payload or {}, ensure_ascii=False),
        )
    )


# ---------------------------------------------------------------- 创建订单
def _build_pay_params(order: Order) -> dict:
    channel = order.channel
    if settings.payment_mock:
        return {
            "channel": channel,
            "mode": "mock",
            "order_id": order.id,
            "amount_cents": order.amount,
            "qr_content": f"bizfast://mock-pay/{order.id}",
            "redirect_url": None,
            "prepay_id": None,
            "notice": "本地模拟支付：请在页面上点击「我已完成支付」以模拟渠道回调",
        }

    # 真实渠道参数（网关需配置 WECHAT_MCH_ID / ALIPAY_APP_ID 等环境变量）
    mode = {
        "wechat": "jsapi",
        "alipay": "qrcode",
        "apple": "iap",
        "huawei": "iap",
    }.get(channel, "qrcode")
    return {
        "channel": channel,
        "mode": mode,
        "order_id": order.id,
        "amount_cents": order.amount,
        "qr_content": None,
        "redirect_url": None,
        "prepay_id": None,
        "notice": "正式支付渠道尚未配置商户参数，请先在环境变量中补齐渠道密钥",
    }


async def create_order(db, owner: OwnerContext, payload, client_ip: str | None = None) -> dict:
    """创建支付订单（幂等 + 券核销 + 风控）。"""
    plan = payload.plan
    if plan not in PLAN_NAMES:
        raise BizError(40001, "请选择有效的购买方案")
    amount = plan_price(plan)
    platform = payload.platform or "web"
    channel = pay_channel_for(platform)
    match_id = payload.match_id if plan == "single" else None

    user = await ensure_owner_user(db, owner)
    user_id = user.id

    # 幂等 1：显式 Idempotency-Key
    if payload.idempotency_key:
        exist = (
            await db.execute(
                select(Order).where(Order.idempotency_key == payload.idempotency_key)
            )
        ).scalar_one_or_none()
        if exist is not None:
            return _create_out(exist, reused=True)

    # 幂等 2：同一用户 + 同一商机的「进行中」订单直接复用，避免重复扣款
    if match_id:
        exist = (
            await db.execute(
                select(Order).where(
                    Order.user_id == user_id,
                    Order.match_id == match_id,
                    Order.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one_or_none()
        if exist is not None:
            if exist.status == "pending" and _is_expired(exist):
                await _close_order(db, exist)
                await db.commit()
            else:
                return _create_out(exist, reused=True)

    # M5-09：优惠券 / 邀请码（先校验再落单，失败直接给中文原因）
    coupon_code = coupon_service.normalize_code(getattr(payload, "coupon_code", None))
    discount = 0
    if coupon_code:
        preview = await coupon_service.validate_coupon(db, owner.owner_key, coupon_code, plan, amount)
        discount = int(preview["discount_cents"])
    final_amount = amount - discount

    # M5-10：风控体检（命中只标记人工审核，不阻断真实用户）
    risk_flag = await risk_service.evaluate_order_risk(db, owner.owner_key, client_ip)

    # M5-08：会员自动续费意向（仅月/年会员有意义；默认关闭，需用户显式开启）
    auto_renew = getattr(payload, "auto_renew", None)
    if plan in ("month", "year") and auto_renew is not None:
        user.auto_renew = bool(auto_renew)

    order = Order(
        id=str(uuid.uuid4()),
        user_id=user_id,
        plan=plan,
        amount=final_amount,
        platform=platform,
        channel=channel,
        status="pending",
        match_id=match_id,
        idempotency_key=payload.idempotency_key,
        coupon_code=coupon_code or None,
        discount_cents=discount,
        risk_flag=risk_flag,
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError:
        # 并发下同时下单：唯一索引兜底，转为复用既有进行中订单（M5-06 不漏单、不重复扣款）
        await db.rollback()
        exist = (
            await db.execute(
                select(Order).where(
                    Order.user_id == user_id,
                    Order.match_id == match_id,
                    Order.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalar_one_or_none()
        if exist is not None:
            return _create_out(exist, reused=True)
        raise

    if coupon_code and discount > 0:
        await coupon_service.redeem(db, owner.owner_key, coupon_code, order.id, discount)
    if risk_flag:
        # 给用户一条透明的中文说明，而不是让他「莫名被拦」
        await notify_service.create_notification_for_user(
            db,
            user_id,
            category="system",
            title="订单已进入人工审核",
            content=risk_service.REVIEW_NOTICE,
            link=f"/pages/m5_pay/index?orderId={order.id}",
        )

    _record(
        db,
        order.id,
        channel,
        "create",
        "pending",
        {"plan": plan, "amount": final_amount, "coupon": coupon_code or None, "discount": discount},
    )
    await db.commit()
    await db.refresh(order)

    if not settings.payment_mock:
        logger.info("订单 %s 需调用 %s 网关下单", order.id, channel)

    return _create_out(order, reused=False)


def _create_out(order: Order, reused: bool) -> dict:
    return {
        "order_id": order.id,
        "plan": order.plan,
        "amount_cents": order.amount,
        "amount_label": amount_label(order.amount),
        "original_cents": order.amount + (order.discount_cents or 0),
        "original_label": amount_label(order.amount + (order.discount_cents or 0)),
        "discount_cents": order.discount_cents or 0,
        "discount_label": amount_label(order.discount_cents or 0),
        "coupon_code": order.coupon_code,
        "channel": order.channel,
        "status": order.status,
        "pay_params": _build_pay_params(order),
        "reused": reused,
        "risk": risk_service.risk_payload(order.risk_flag),
    }


# ---------------------------------------------------------------- 状态流转
def _is_expired(order: Order) -> bool:
    if order.status != "pending":
        return False
    created = order.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return _now() - created > timedelta(minutes=settings.order_expire_minutes)


async def _close_order(db, order: Order) -> None:
    order.status = "closed"
    order.closed_at = _now()
    _record(db, order.id, order.channel, "close", "closed", {"reason": "超时未支付"})


async def _transition(db, order: Order, target: str) -> None:
    if target not in TRANSITIONS.get(order.status, set()):
        raise BizError(40901, f"订单当前状态为{STATUS_LABELS.get(order.status, order.status)}，无法执行该操作")
    order.status = target
    now = _now()
    if target == "paid":
        order.paid_at = now
    elif target == "generating":
        order.generating_at = now
    elif target == "delivered":
        order.delivered_at = now
    elif target == "refunded":
        order.refunded_at = now
    elif target == "closed":
        order.closed_at = now


async def _grant_plan(db, order: Order) -> None:
    """支付成功后发放权益（单次/月度/年度）。"""
    from app.models import User

    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    if user is None:
        return
    if order.plan == "single":
        if user.plan == "none":
            user.plan = "single"
        return
    days = 30 if order.plan == "month" else 365
    base = user.plan_expire_at
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    start = base if (base and base > _now()) else _now()
    user.plan = order.plan
    user.plan_expire_at = start + timedelta(days=days)


# ---------------------------------------------------------------- 自动续费（M5-08）
def _renew_notice_days() -> int:
    return int(getattr(settings, "renew_notice_days", 3))


async def membership_quota(db, user) -> dict:
    """M0-03（V5.0）：会员额度 —— 已购次数 / 已用启动包数 / 额度剩余。

    月/年会员不限量（`quota_unlimited=true`，`quota_remaining=-1`）；
    单次购买按「一单一次生成」计额度，已用 = 已生成的启动包数，
    方便用户与后台对齐「还剩几次」，也方便后台做额度巡检。
    """
    from app.models import Package

    purchased = (
        await db.execute(
            select(func.count(Order.id)).where(
                Order.user_id == user.id,
                Order.status.in_(["paid", "generating", "delivered", "refunded"]),
            )
        )
    ).scalar_one()
    used = (
        await db.execute(select(func.count(Package.id)).where(Package.user_id == user.id))
    ).scalar_one()
    limited = user.plan not in ("month", "year")
    total = int(purchased or 0) if limited else 0
    return {
        "purchased_count": int(purchased or 0),
        "used_package_count": int(used or 0),
        "quota_total": total,
        "quota_remaining": max(0, total - int(used or 0)) if limited else -1,
        "quota_unlimited": not limited,
    }


def subscription_payload(user) -> dict:
    """订阅状态（M5-08）。取消入口在 UI 上只需 1 步，且可随时关闭。"""
    expire = user.plan_expire_at
    if expire is not None and expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    days_left = None
    if expire is not None:
        days_left = max(0, (expire - _now()).days)
    renew_at = None
    if user.auto_renew and expire is not None and user.plan in ("month", "year"):
        renew_at = expire
    return {
        "plan": user.plan,
        "plan_name": PLAN_NAMES.get(user.plan, user.plan),
        "is_member": user.plan in ("month", "year"),
        "auto_renew": bool(user.auto_renew),
        # 只有月/年会员才谈得上自动续费；单次包不适用
        "renewable": user.plan in ("month", "year"),
        "expire_at": _iso(expire),
        "days_left": days_left,
        "renew_at": _iso(renew_at),
        "renew_notice_days": _renew_notice_days(),
        "notice": (
            "已开启自动续费，到期前 3 天会提醒你，可随时一键取消。"
            if user.auto_renew
            else "未开启自动续费，到期后会员权益将停止，不会自动扣款。"
        ),
        "price_cents": plan_price(user.plan) if user.plan in ("month", "year") else 0,
        "price_label": amount_label(plan_price(user.plan)) if user.plan in ("month", "year") else "",
    }


async def _resolve_user(db, owner: OwnerContext):
    from app.models import User

    return await ensure_owner_user(db, owner)


async def get_subscription(db, owner: OwnerContext) -> dict:
    user = await _resolve_user(db, owner)
    await maybe_notify_renewal(db, user)
    await db.commit()
    payload = subscription_payload(user)
    # M0-03（V5.0）：同屏带上额度信息（已购次数 / 已用启动包数 / 额度剩余）
    payload.update(await membership_quota(db, user))
    return payload


async def update_subscription(db, owner: OwnerContext, auto_renew: bool) -> dict:
    """开启/关闭自动续费（取消也是一步，无任何障碍）。"""
    user = await _resolve_user(db, owner)
    if auto_renew and user.plan not in ("month", "year"):
        raise BizError(40301, "自动续费仅适用于月度 / 年度会员，请先开通会员")
    user.auto_renew = bool(auto_renew)
    if not auto_renew:
        user.renew_notified_at = None
    await db.commit()
    await db.refresh(user)
    return subscription_payload(user)


async def cancel_subscription(db, owner: OwnerContext) -> dict:
    """一键取消自动续费（PRD：取消入口不超过 3 步，不允许设置取消障碍）。"""
    result = await update_subscription(db, owner, False)
    result["message"] = "已取消自动续费，到期后不再扣款，会员权益可用到到期日。"
    return result


async def maybe_notify_renewal(db, user) -> bool:
    """M0-03（V5.0）：会员到期前 3 天 / 1 天各自动提醒一次续费。

    与 M5-08 相比有两处变化：
    1. 不再以「已开启自动续费」为前提 —— 未开启的用户同样要提前知道会员即将到期，
       否则会静默失去权益而流失；
    2. 从「只提醒一次」改为「3 天、1 天两档各提醒一次」，用 `renew_stage` 档位去重。
    """
    if not user or user.plan not in ("month", "year"):
        return False
    expire = user.plan_expire_at
    if expire is None:
        return False
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    remaining = (expire - _now()).days

    # 两个提醒档位：到期前 3 天 / 1 天，各自只发一次
    if remaining <= 1:
        stage = 1
    elif remaining <= _renew_notice_days():
        stage = _renew_notice_days()
    else:
        return False

    notified = user.renew_notified_at
    if notified is not None and notified.tzinfo is None:
        notified = notified.replace(tzinfo=timezone.utc)
    # 同一档位已提醒过就不再打扰（避免每次拉取会员页都重复推送）
    if user.renew_stage == stage and notified is not None:
        return False

    plan_name = PLAN_NAMES.get(user.plan, user.plan)
    if user.auto_renew:
        title = f"会员将在 {max(0, remaining)} 天后自动续费"
        content = (
            f"你的{plan_name}将于 {expire.date().isoformat()} 到期，"
            f"届时将自动续费 ¥{amount_label(plan_price(user.plan))}。"
            "如需取消，可在会员页一键关闭自动续费。"
        )
    else:
        title = f"会员将在 {max(0, remaining)} 天后到期"
        content = (
            f"你的{plan_name}将于 {expire.date().isoformat()} 到期，"
            "到期后会员权益将停止。续费后可继续无限次生成启动包并保留工具箱权益。"
        )

    await notify_service.create_notification_for_user(
        db,
        user.id,
        category="order",
        title=title,
        content=content,
        link="/pages/m5_pay/index",
    )
    user.renew_notified_at = _now()
    user.renew_stage = stage
    return True


async def mark_paid(db, order: Order, source: str, payload: dict | None = None) -> bool:
    """把订单置为已支付（幂等）。返回 True 表示本次是首次置为已支付。"""
    if order.status != "pending":
        _record(db, order.id, order.channel, source, order.status, {"duplicated": True})
        return False
    await _transition(db, order, "paid")
    _record(db, order.id, order.channel, source, "paid", payload)
    await _grant_plan(db, order)
    await notify_service.create_notification_for_user(
        db,
        order.user_id,
        category="order",
        title="支付成功，正在为你生成启动包",
        content=f"订单 {order.id[:8]} 已支付成功，金额 ¥{amount_label(order.amount)}。生成完成后会第一时间通知你。",
        link=f"/pages/m5_pay/index?orderId={order.id}",
    )
    return True


# ---------------------------------------------------------------- 回调 / 查单
async def handle_callback(db, channel: str, body: dict) -> dict:
    """M5-06：接收渠道回调后更新订单（幂等，重复回调不重复发货）。"""
    order_id = body.get("order_id") or body.get("out_trade_no")
    if not order_id:
        raise BizError(40001, "支付回调缺少订单号")
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise BizError(40401, "未找到对应订单")
    if channel != order.channel:
        raise BizError(60001, "支付渠道与订单不一致，请重新支付")

    success = str(body.get("result", "success")).lower() in ("success", "ok", "true", "paid")
    if not success:
        _record(db, order.id, channel, "callback", "fail", body)
        await db.commit()
        raise BizError(60001)

    if not settings.payment_mock and not _verify_signature(channel, body):
        _record(db, order.id, channel, "callback", "sign_error", body)
        await db.commit()
        raise BizError(60001, "支付回调验签失败，请重新支付")

    first = await mark_paid(db, order, "callback", body)
    await db.commit()
    await db.refresh(order)
    return {
        "order_id": order.id,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "duplicated": not first,
        "message": "支付成功，正在为你生成启动包" if first else "该订单已支付，无需重复处理",
    }


def _verify_signature(channel: str, body: dict) -> bool:
    """真实渠道验签。未配置商户密钥时 fail-closed。"""
    import os

    secret = {
        "wechat": os.getenv("WECHAT_API_KEY"),
        "alipay": os.getenv("ALIPAY_APP_ID"),
        "apple": os.getenv("APPLE_SHARED_SECRET"),
        "huawei": os.getenv("HUAWEI_APP_ID"),
    }.get(channel)
    if not secret:
        return False
    # 真实实现：按渠道文档校验签名后返回结果
    return bool(body.get("sign"))


# ---------------------------------------------------------------- 主动查单兜底（M2-01 / 第 10.2 节）
# PRD：所有支付回调必须主动查单，绝不只靠回调判断支付状态，防止漏单。
# 渠道侧「已扣款」与本地「已支付」是两件事：回调丢失时本地会停在待支付，
# 必须由主动查单向渠道确认后补单，否则用户付了钱却拿不到货 —— 这是致命事故。
_MOCK_CHANNEL_PAID = "paymock:channel_paid:{order_id}"


async def mark_mock_channel_paid(order_id: str) -> None:
    """本地模拟渠道侧已扣款（**不回写本地订单**）。

    用于验收「回调丢失 → 主动查单补单」这一条防漏单链路：调用后本地订单仍为待支付，
    只有主动查单才应该把它补成已支付。真实环境由渠道网关承担这个角色。
    """
    from app.core.cache import get_cache

    await get_cache().set(_MOCK_CHANNEL_PAID.format(order_id=order_id), "1", ttl=6 * 3600)


async def channel_query(channel: str, order_id: str) -> str:
    """主动向支付渠道查询订单真实支付状态，返回 paid / pending / unknown。

    - 未配置真实渠道（PAYMENT_MOCK=true）：读渠道侧模拟标记。默认 unknown，
      只有显式模拟「渠道已扣款」后才返回 paid（避免把用户没付的钱误判成已付）。
    - 真实渠道：需补齐商户密钥后调用网关查单接口；密钥缺失时返回 unknown
      （fail-safe：宁可交给人工核对，也不擅自发货）。
    """
    if settings.payment_mock:
        from app.core.cache import get_cache

        marker = await get_cache().get(_MOCK_CHANNEL_PAID.format(order_id=order_id))
        return "paid" if marker else "unknown"

    import os

    secret = {
        "wechat": os.getenv("WECHAT_API_KEY"),
        "alipay": os.getenv("ALIPAY_APP_ID"),
        "apple": os.getenv("APPLE_SHARED_SECRET"),
        "huawei": os.getenv("HUAWEI_APP_ID"),
    }.get(channel)
    if not secret:
        return "unknown"
    # 真实网关查单接口待接入：拿到结果后按 paid / pending / unknown 返回
    return "unknown"


async def recover_pending_order(db, order: Order) -> bool:
    """主动查单补单：渠道已扣款而本地仍待支付 → 补成已支付（幂等）。"""
    if order.status != "pending":
        return False
    if await channel_query(order.channel, order.id) != "paid":
        return False
    first = await mark_paid(db, order, "query", {"recovered": True, "reason": "callback_missing"})
    _record(db, order.id, order.channel, "query", "recovered" if first else order.status,
            {"reason": "主动查单发现渠道已扣款"})
    await db.commit()
    await db.refresh(order)
    return first


async def package_brief(db, order_id: str) -> tuple[str | None, str | None]:
    """查询订单关联的《生意启动包》（由 M4 / B 模块落库）。

    刻意用显式查询而不是 `order.package` 懒加载：在 async 会话里访问未加载的
    关系属性会触发同步 IO，直接抛 MissingGreenlet。
    """
    from app.models import Package

    row = (
        await db.execute(select(Package).where(Package.order_id == order_id))
    ).scalar_one_or_none()
    if row is None:
        return None, None
    return row.id, row.status


async def query_order(db, order_id: str, owner: OwnerContext | None = None) -> Order:
    """主动查单兜底（M5-06 / 第 10.2 节）。

    绝不只靠回调判断支付状态：待支付订单会主动向渠道查单，
    渠道已扣款则立即补单（防漏单）；同时顺带关闭超时未支付订单。
    """
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise BizError(40401, "未找到该订单")
    if owner is not None and owner.user_id and order.user_id != owner.user_id:
        raise BizError(40401, "未找到该订单")

    # 1) 主动查单：渠道已扣款而本地还是待支付 → 补单（回调丢失兜底）
    if order.status == "pending" and not _is_expired(order):
        try:
            await recover_pending_order(db, order)
        except Exception as exc:  # 查单失败不影响接口可用性
            logger.warning("主动查单失败：%s", exc)

    # 2) 超时未支付 → 关单
    if _is_expired(order):
        await _close_order(db, order)
        _record(db, order.id, order.channel, "query", "closed", {"reason": "主动查单发现超时"})
        await db.commit()
    else:
        _record(db, order.id, order.channel, "query", order.status, None)
        await db.commit()
    await db.refresh(order)
    return order


# ---------------------------------------------------------------- 交付物下载标记（M2-05 / V5.0）
async def record_download(db, order_id: str) -> bool:
    """M2-05（V5.0）：记录交付物**首次**下载时间。

    这个标记直接决定退款路径：
    - 未下载 → 用户可自助发起并**立即全额退款**；
    - 已下载 → 退款必须转人工审核（后台一键处理）。
    幂等：只写第一次时间，重复下载不覆盖。
    """
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        return False
    if order.downloaded_at is not None:
        return False
    order.downloaded_at = _now()
    await db.commit()
    return True


async def _revoke_plan(db, order: Order) -> bool:
    """M2-05（V5.0）：退款后自动回收会员权益。

    - 月卡 / 年卡：把 plan 收回 none，清掉到期日与自动续费；
    - 单次礼包：仅当用户没有其它「仍在生效」的单次订单时才回收，
      避免退款一单把其它已购单次的权益也误伤。
    """
    from app.models import User

    user = (await db.execute(select(User).where(User.id == order.user_id))).scalar_one_or_none()
    if user is None or user.plan != order.plan:
        return False

    if order.plan in ("month", "year"):
        user.plan = "none"
        user.plan_expire_at = None
        user.auto_renew = False
        user.renew_notified_at = None
        user.renew_stage = None
        return True

    if order.plan == "single":
        others = (
            await db.execute(
                select(func.count(Order.id)).where(
                    Order.user_id == order.user_id,
                    Order.plan == "single",
                    Order.id != order.id,
                    Order.status.in_(["paid", "generating", "delivered"]),
                )
            )
        ).scalar_one()
        if int(others or 0) == 0:
            user.plan = "none"
            return True
    return False


# ---------------------------------------------------------------- 退款（M2-05 / V5.0）
async def refund_order(db, owner: OwnerContext, order_id: str, reason: str | None) -> dict:
    order = await query_order(db, order_id, owner)

    if order.status == "pending":
        raise BizError(60001, "该订单尚未支付，无需退款")
    if order.status == "closed":
        raise BizError(40301, "该订单已关闭，无需退款")
    if order.status == "refunded":
        raise BizError(40301, "该订单已退款，请勿重复申请")
    if order.status == "generating":
        raise BizError(40901, "订单正在生成中，请稍候再试")
    if order.refund_review == "pending":
        raise BizError(40901, "退款申请已提交，正在人工审核，请耐心等待")

    base = order.delivered_at or order.paid_at
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    if base is None or _now() - base > timedelta(days=settings.refund_window_days):
        raise BizError(
            40301, f"已超过 {settings.refund_window_days} 天无理由退款期限，请联系客服处理"
        )

    # M5-10：疑似恶意退款（频繁退款）标记人工审核；不设置取消障碍
    already = await risk_service.evaluate_refund_risk(db, owner.owner_key)

    # —— V5.0 M2-05：交付物已下载 → 不走自助退款，转人工审核 ——
    if order.downloaded_at is not None:
        order.refund_review = "pending"
        order.refund_reason = (reason or "用户申请（交付物已下载）")[:255]
        if already:
            order.risk_flag = order.risk_flag or already
        await notify_service.create_notification_for_user(
            db,
            order.user_id,
            category="refund",
            title="退款申请已提交，正在人工审核",
            content=(
                f"订单 {order.id[:8]} 的交付物已下载，退款需人工审核，"
                "我们会在 24 小时内处理完毕并通知你。"
            ),
            link=f"/pages/m5_pay/index?orderId={order.id}",
        )
        # M2-04：让后台「订单管理」立刻可见（不必等 5 分钟轮询）+ 推送告警
        try:
            from app.services import automation as automation_service

            await automation_service.raise_alert(
                db,
                alert_type="refund_review",
                level="warning",
                title=f"退款待审核：{order.id[:8]}（交付物已下载）",
                content=(
                    f"订单 {order.id}（{order.plan}，金额 ¥{amount_label(order.amount)}）"
                    f"的交付物已下载，用户申请退款：{order.refund_reason}。"
                    "请到「订单管理」一键处理（同意退款 / 驳回）。"
                ),
                related_type="order",
                related_id=order.id,
                fingerprint=f"refund_review:{order.id}",
            )
        except Exception as exc:  # 告警失败不能影响退款申请本身
            logger.warning("退款审核告警写入失败：order=%s err=%s", order.id, exc)

        await db.commit()
        await db.refresh(order)
        return {
            "order_id": order.id,
            "status": order.status,
            "status_label": STATUS_LABELS.get(order.status, order.status),
            "review": "pending",
            "review_required": True,
            "refunded_at": None,
            "message": "交付物已下载，退款申请已提交人工审核，24 小时内处理完毕",
        }

    # —— 未下载：自助全额退款，即时生效 ——
    await risk_service.record_event(db, owner.owner_key, "refund_done", risk_service.LEVEL_NORMAL)
    if already:
        order.risk_flag = order.risk_flag or already

    await _transition(db, order, "refunded")
    order.refund_review = "auto_approved"
    # V5.0 M2-05：退款后会员权益自动回收
    revoked = await _revoke_plan(db, order)
    # 券已核销但订单退款：释放用户额度，允许再次使用（避免用户因退款而永久失去优惠）
    await coupon_service.release_on_refund(db, order.id)
    _record(db, order.id, order.channel, "refund", "refunded", {"reason": reason or "用户申请"})
    await notify_service.create_notification_for_user(
        db,
        order.user_id,
        category="refund",
        title="退款已受理",
        content=f"订单 {order.id[:8]} 的退款申请已受理，退款将在 24 小时内原路到账。",
        link=f"/pages/m5_pay/index?orderId={order.id}",
    )
    await db.commit()
    await db.refresh(order)
    return {
        "order_id": order.id,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "review": "auto_approved",
        "review_required": False,
        "rights_revoked": revoked,
        "refunded_at": _iso(order.refunded_at),
        "message": f"退款已受理，将在 24 小时内原路退还 ¥{amount_label(order.amount)}",
    }


async def approve_refund_review(db, order_id: str) -> dict:
    """后台审核通过已下载订单的退款（M2-05 + M4-03 一键处理）。"""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise BizError(40401, "订单不存在")
    if order.status == "refunded":
        return {"order_id": order.id, "status": "refunded", "revoked": False}

    await _transition(db, order, "refunded")
    order.refund_review = "approved"
    revoked = await _revoke_plan(db, order)
    await coupon_service.release_on_refund(db, order.id)
    _record(db, order.id, order.channel, "refund", "refunded", {"reason": "后台审核通过"})
    await notify_service.create_notification_for_user(
        db,
        order.user_id,
        category="refund",
        title="退款已受理",
        content=f"订单 {order.id[:8]} 的退款审核已通过，退款将在 24 小时内原路到账。",
        link=f"/pages/m5_pay/index?orderId={order.id}",
    )
    await db.commit()
    return {"order_id": order.id, "status": "refunded", "revoked": revoked}


async def reject_refund_review(db, order_id: str, reason: str | None = None) -> dict:
    """后台驳回已下载订单的退款申请（M2-05）。"""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise BizError(40401, "订单不存在")
    order.refund_review = "rejected"
    order.refund_reason = (reason or order.refund_reason or "")[:255]
    await notify_service.create_notification_for_user(
        db,
        order.user_id,
        category="refund",
        title="退款申请未通过",
        content=(
            f"订单 {order.id[:8]} 的退款申请未通过：{reason or '交付物已下载使用'}。"
            "如有疑问可在交付页提交反馈，我们会尽快联系你。"
        ),
        link=f"/pages/m5_pay/index?orderId={order.id}",
    )
    await db.commit()
    return {"order_id": order.id, "status": order.status, "review": "rejected"}


# ---------------------------------------------------------------- 供 B 模块驱动状态机
async def mark_generating(db, order_id: str) -> None:
    """M4 生成任务启动时调用（B 模块）。"""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None or order.status != "paid":
        return
    await _transition(db, order, "generating")
    await db.commit()


async def mark_delivered(db, order_id: str) -> None:
    """M4 生成完成后调用（B 模块）。"""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None or order.status != "generating":
        return
    await _transition(db, order, "delivered")
    await notify_service.create_notification_for_user(
        db,
        order.user_id,
        category="package",
        title="你的生意启动包已生成",
        content="10 件交付物已全部生成，可立即下载。祝开业大吉，生意兴隆。",
        link=f"/pages/m5_pay/index?orderId={order.id}",
    )
    await db.commit()


# ---------------------------------------------------------------- 输出
def order_payload(db_order: Order, package_id: str | None = None, package_status: str | None = None) -> dict:
    index = TIMELINE_STEPS.index(db_order.status) if db_order.status in TIMELINE_STEPS else None
    timeline = []
    for i, step in enumerate(TIMELINE_STEPS):
        at = {
            "pending": db_order.created_at,
            "paid": db_order.paid_at,
            "generating": db_order.generating_at,
            "delivered": db_order.delivered_at,
        }[step]
        timeline.append(
            {
                "status": step,
                "label": STATUS_LABELS[step],
                "at": _iso(at),
                "done": index is not None and i <= index,
                "active": db_order.status == step,
            }
        )
    if db_order.status in ("refunded", "closed"):
        timeline.append(
            {
                "status": db_order.status,
                "label": STATUS_LABELS[db_order.status],
                "at": _iso(db_order.refunded_at or db_order.closed_at),
                "done": True,
                "active": True,
            }
        )

    base = db_order.delivered_at or db_order.paid_at
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    window_ok = base is not None and _now() - base <= timedelta(days=settings.refund_window_days)
    # M2-05（V5.0）：未下载 → 自助全额退款即时生效；已下载 → 仍可发起，但要转人工审核
    downloaded = db_order.downloaded_at is not None
    reviewing = db_order.refund_review == "pending"
    can_refund = db_order.status in ("paid", "delivered") and window_ok and not reviewing
    deadline = (base + timedelta(days=settings.refund_window_days)) if base else None
    if reviewing:
        refund_notice = "退款申请已提交人工审核，24 小时内处理完毕。"
    elif downloaded:
        refund_notice = "交付物已下载，退款需人工审核；提交后 24 小时内处理完毕。"
    else:
        refund_notice = "交付物尚未下载，可自助全额退款，24 小时内原路到账。"

    return {
        "id": db_order.id,
        "plan": db_order.plan,
        "plan_name": PLAN_NAMES.get(db_order.plan, db_order.plan),
        "amount_cents": db_order.amount,
        "amount_label": amount_label(db_order.amount),
        "original_cents": db_order.amount + (db_order.discount_cents or 0),
        "original_label": amount_label(db_order.amount + (db_order.discount_cents or 0)),
        "discount_cents": db_order.discount_cents or 0,
        "discount_label": amount_label(db_order.discount_cents or 0),
        "coupon_code": db_order.coupon_code,
        "platform": db_order.platform,
        "channel": db_order.channel,
        "status": db_order.status,
        "status_label": STATUS_LABELS.get(db_order.status, db_order.status),
        "match_id": db_order.match_id,
        "package_id": package_id,
        "package_status": package_status,
        "created_at": _iso(db_order.created_at),
        "paid_at": _iso(db_order.paid_at),
        "generating_at": _iso(db_order.generating_at),
        "delivered_at": _iso(db_order.delivered_at),
        "refunded_at": _iso(db_order.refunded_at),
        "closed_at": _iso(db_order.closed_at),
        "timeline": timeline,
        "can_refund": bool(can_refund),
        # ---- M2-05（V5.0）退款路径：self=自助全额退 / review=人工审核 ----
        "downloaded": downloaded,
        "refund_review": db_order.refund_review,
        "refund_reviewing": reviewing,
        "refund_path": "review" if downloaded else "self",
        "refund_notice": refund_notice,
        "refund_deadline": _iso(deadline),
        "risk": risk_service.risk_payload(db_order.risk_flag),
    }
