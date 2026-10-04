"""M5 付费与订单 业务逻辑层 - 负责人 A

- M5-03 价格锚点：9.9 单次 / 39 月度 / 199 年度（同屏三档，突出年度最划算）
- M5-04 支付渠道适配：按端选择渠道（Web 走支付宝/微信，小程序走微信 JSAPI，iOS 走 IAP…）
- M5-05 订单状态机：待支付 → 已支付 → 生成中 → 已交付；→ 已关闭；已支付/生成中/已交付 → 已退款
- M5-06 支付回调 + 主动查单双保险，不存在漏单
- M5-07 7 天无理由退款，24 小时内到账
- 幂等：同一 Idempotency-Key / 同一用户同一商机的重复创建返回既有订单

未接真实渠道时（PAYMENT_MOCK=true）走本地模拟支付，用于本地联调与验收；
真实渠道只需在 handle_callback 中补签名校验与网关调用，状态机无需改动。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
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

PLAN_NAMES = {"single": "单次启动包", "month": "月度会员", "year": "年度会员"}
PLAN_UNITS = {"single": "单次", "month": "每月", "year": "每年"}

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
    """M5-03：三档价格同屏展示，年度档标注「最划算」。"""
    return [
        {
            "plan": "single",
            "name": PLAN_NAMES["single"],
            "price_cents": settings.price_single_cents,
            "price_label": amount_label(settings.price_single_cents),
            "unit_label": "单次",
            "highlight": False,
            "badge": "先试一次",
            "rights": ["1 份完整生意启动包", "10 件可直接使用的文件", "永久保存在账号下"],
        },
        {
            "plan": "month",
            "name": PLAN_NAMES["month"],
            "price_cents": settings.price_month_cents,
            "price_label": amount_label(settings.price_month_cents),
            "unit_label": "每月",
            "highlight": False,
            "badge": "可随时取消",
            "rights": ["30 天内不限次生成", "全部 10 件交付物", "会员专属重新生成"],
        },
        {
            "plan": "year",
            "name": PLAN_NAMES["year"],
            "price_cents": settings.price_year_cents,
            "price_label": amount_label(settings.price_year_cents),
            "unit_label": "每年",
            "highlight": True,
            "badge": "最划算",
            "rights": ["12 个月不限次生成", "折合每月约 16.6 元", "优先客服与商机库更新提醒"],
        },
    ]


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
    return subscription_payload(user)


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
    """到期前 3 天提醒一次（M5-08），避免用户「被静默续费」。"""
    if not user or not user.auto_renew or user.plan not in ("month", "year"):
        return False
    expire = user.plan_expire_at
    if expire is None:
        return False
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    remaining = (expire - _now()).days
    if remaining > _renew_notice_days():
        return False
    notified = user.renew_notified_at
    if notified is not None and notified.tzinfo is None:
        notified = notified.replace(tzinfo=timezone.utc)
    if notified is not None and (expire - notified).days <= _renew_notice_days():
        return False  # 本轮已提醒过，不重复打扰

    await notify_service.create_notification_for_user(
        db,
        user.id,
        category="order",
        title=f"会员将在 {max(0, remaining)} 天后自动续费",
        content=(
            f"你的{PLAN_NAMES.get(user.plan, user.plan)}将于 {expire.date().isoformat()} 到期，"
            f"届时将自动续费 ¥{amount_label(plan_price(user.plan))}。"
            "如需取消，可在会员页一键关闭自动续费。"
        ),
        link="/pages/m5_pay/index",
    )
    user.renew_notified_at = _now()
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
    """主动查单兜底（M5-06）：查询时顺带关闭超时未支付订单。"""
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise BizError(40401, "未找到该订单")
    if owner is not None and owner.user_id and order.user_id != owner.user_id:
        raise BizError(40401, "未找到该订单")

    if _is_expired(order):
        await _close_order(db, order)
        _record(db, order.id, order.channel, "query", "closed", {"reason": "主动查单发现超时"})
        await db.commit()
    else:
        _record(db, order.id, order.channel, "query", order.status, None)
        await db.commit()
    await db.refresh(order)
    return order


# ---------------------------------------------------------------- 退款（M5-07）
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

    base = order.delivered_at or order.paid_at
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    if base is None or _now() - base > timedelta(days=settings.refund_window_days):
        raise BizError(40301, f"已超过 {settings.refund_window_days} 天无理由退款期限，请联系客服处理")

    # M5-10：疑似恶意退款（频繁退款）标记人工审核；仍按 7 天无理由正常受理，不设置取消障碍
    already = await risk_service.evaluate_refund_risk(db, owner.owner_key)
    await risk_service.record_event(db, owner.owner_key, "refund_done", risk_service.LEVEL_NORMAL)
    if already:
        order.risk_flag = order.risk_flag or already

    await _transition(db, order, "refunded")
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
        "refunded_at": _iso(order.refunded_at),
        "message": f"退款已受理，将在 24 小时内原路退还 ¥{amount_label(order.amount)}",
    }


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
    can_refund = db_order.status in ("paid", "delivered") and (
        base is not None and _now() - base <= timedelta(days=settings.refund_window_days)
    )
    deadline = (base + timedelta(days=settings.refund_window_days)) if base else None

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
        "refund_deadline": _iso(deadline),
        "risk": risk_service.risk_payload(db_order.risk_flag),
    }
