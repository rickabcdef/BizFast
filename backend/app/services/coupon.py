"""M5-09 优惠券与邀请码 - 负责人 A

PRD 验收：**优惠券不可叠加使用，规则在页面明示**。

设计要点：
- 券（coupon）与邀请码（invite）走同一套核销表，`CouponRedemption.order_id` 唯一
  → 一个订单物理上只可能核销一张，从数据层杜绝叠加。
- 校验失败一律返回中文 `BizError`，并把「不可叠加」等规则随成功响应一起下发，
  由前端原样展示，避免出现「页面没说清楚」的投诉。
- 目录（`COUPON_CATALOG`）用于本地/演示环境播种；生产由运营后台维护。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.errors import BizError
from app.models import Coupon, CouponRedemption
from app.services.money import amount_label

# 规则文案：接口在成功/失败时都会带上，前端必须原样展示（PRD 要求规则明示）
RULES_TEXT = "优惠券不可叠加使用，同一订单只能核销一张；邀请码与优惠券同理，不支持叠加。"

# 演示/本地环境种子目录（生产由运营后台写入 coupons 表）
COUPON_CATALOG = [
    {
        "code": "WELCOME5",
        "kind": "coupon",
        "title": "新人立减 5 元",
        "discount_type": "amount",
        "value": 500,  # 分
        "plan_scope": "",
        "min_amount": 990,
        "total_quota": 0,
        "per_user_limit": 1,
    },
    {
        "code": "YEAR20",
        "kind": "coupon",
        "title": "年度会员立减 20 元",
        "discount_type": "amount",
        "value": 2000,
        "plan_scope": "year",
        "min_amount": 19900,
        "total_quota": 0,
        "per_user_limit": 1,
    },
    {
        "code": "INVITE10",
        "kind": "invite",
        "title": "好友邀请码 9 折",
        "discount_type": "percent",
        "value": 10,  # 减免 10%
        "plan_scope": "",
        "min_amount": 0,
        "total_quota": 0,
        "per_user_limit": 1,
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_code(code: str | None) -> str:
    return (code or "").strip().upper()


async def seed_catalog(db) -> None:
    """幂等播种：已存在的券不覆盖，避免抹掉线上运营配置。"""
    existing = {
        c.code for c in (await db.execute(select(Coupon))).scalars().all()
    }
    added = False
    for item in COUPON_CATALOG:
        if item["code"] in existing:
            continue
        db.add(Coupon(**item, active=True))
        added = True
    if added:
        await db.commit()


async def get_coupon(db, code: str) -> Coupon | None:
    return (await db.execute(select(Coupon).where(Coupon.code == code))).scalar_one_or_none()


def compute_discount(coupon: Coupon, amount_cents: int) -> int:
    """计算减免金额（分）。减免不会超过订单金额本身。"""
    if coupon.discount_type == "percent":
        discount = int(round(amount_cents * min(100, max(0, coupon.value)) / 100))
    else:
        discount = int(coupon.value)
    return max(0, min(discount, amount_cents))


def _used_by_owner(db, owner_key: str, code: str):
    return db.execute(
        select(func.count()).select_from(CouponRedemption).where(
            CouponRedemption.owner_key == owner_key, CouponRedemption.code == code
        )
    )


async def validate_coupon(db, owner_key: str, code: str | None, plan: str, amount_cents: int) -> dict:
    """预校验：不落库、不占用额度，只回传「能减多少 + 规则」。

    失败时抛中文 BizError，前端直接展示 message。
    """
    normalized = normalize_code(code)
    if not normalized:
        raise BizError(40001, "请输入优惠券或邀请码")

    coupon = await get_coupon(db, normalized)
    if coupon is None or not coupon.active:
        raise BizError(40301, "这个优惠码不存在或已失效，请检查后重新输入")

    expires = coupon.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is not None and expires < _now():
        raise BizError(40301, "这个优惠码已过期，请使用其他优惠码")

    if coupon.plan_scope and plan not in [p for p in coupon.plan_scope.split(",") if p]:
        raise BizError(40301, f"这个优惠码仅适用于{_plan_scope_label(coupon.plan_scope)}，换个方案试试")

    if amount_cents < coupon.min_amount:
        raise BizError(
            40301,
            f"订单金额满 ¥{coupon.min_amount / 100:.0f} 才能使用这个优惠码",
        )

    used = (await _used_by_owner(db, owner_key, normalized)).scalar_one()
    if coupon.per_user_limit and used >= coupon.per_user_limit:
        raise BizError(40301, "这个优惠码你已经用过了，每个账号限用一次")

    if coupon.total_quota and coupon.used_count >= coupon.total_quota:
        raise BizError(40301, "这个优惠码已被领完，下次早点来")

    discount = compute_discount(coupon, amount_cents)
    if discount <= 0:
        raise BizError(40301, "这个优惠码对当前订单没有减免，请使用其他优惠码")

    return {
        "code": coupon.code,
        "kind": coupon.kind,
        "title": coupon.title,
        "discount_cents": discount,
        "discount_label": amount_label(discount),
        "original_cents": amount_cents,
        "original_label": amount_label(amount_cents),
        "final_cents": amount_cents - discount,
        "final_label": amount_label(amount_cents - discount),
        "rules": RULES_TEXT,
        "notice": f"已使用「{coupon.title}」，立减 ¥{amount_label(discount)}",
    }


def _plan_scope_label(scope: str) -> str:
    names = {"single": "单次启动包", "month": "月度会员", "year": "年度会员"}
    return "、".join(names.get(p, p) for p in scope.split(",") if p)


async def redeem(db, owner_key: str, code: str, order_id: str, discount_cents: int) -> None:
    """核销。`order_id` 唯一约束保证同一订单只能核销一张券（不可叠加）。"""
    normalized = normalize_code(code)
    coupon = await get_coupon(db, normalized)
    db.add(
        CouponRedemption(
            id=str(uuid.uuid4()),
            code=normalized,
            owner_key=owner_key,
            order_id=order_id,
            discount_cents=discount_cents,
        )
    )
    if coupon is not None:
        coupon.used_count = (coupon.used_count or 0) + 1


async def release_on_refund(db, order_id: str) -> None:
    """订单退款时释放券额度。

    否则用户「用券下单 → 退款」后会永久失去这张券（per_user_limit 已耗尽），
    属于明显的体验缺陷，也容易被当成「设置取消障碍」。
    """
    row = (
        await db.execute(select(CouponRedemption).where(CouponRedemption.order_id == order_id))
    ).scalar_one_or_none()
    if row is None:
        return
    coupon = await get_coupon(db, row.code)
    if coupon is not None and coupon.used_count > 0:
        coupon.used_count -= 1
    await db.delete(row)


async def list_available(db, owner_key: str) -> list[dict]:
    """可领取/可用的优惠码清单（前端「可用优惠」入口用）。"""
    rows = (await db.execute(select(Coupon).where(Coupon.active.is_(True)))).scalars().all()
    out = []
    for c in rows:
        used = (await _used_by_owner(db, owner_key, c.code)).scalar_one()
        expires = c.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        expired = expires is not None and expires < _now()
        out.append(
            {
                "code": c.code,
                "kind": c.kind,
                "title": c.title,
                "discount_type": c.discount_type,
                "value": c.value,
                "discount_label": (
                    f"减 ¥{amount_label(c.value or 0)}"
                    if c.discount_type == "amount"
                    else f"减 {c.value}%"
                ),
                "plan_scope": c.plan_scope,
                "plan_scope_label": _plan_scope_label(c.plan_scope) if c.plan_scope else "不限方案",
                "min_amount": c.min_amount,
                "usable": (not expired) and used < c.per_user_limit,
                "reason": "已过期" if expired else ("已使用过" if used >= c.per_user_limit else ""),
                "expires_at": expires.isoformat().replace("+00:00", "Z") if expires else None,
            }
        )
    return out


def demo_codes_hint() -> str:
    """本地/演示环境给前端的提示，方便验收时直接试。"""
    return "可用优惠码：" + "、".join(c["code"] for c in COUPON_CATALOG)


def default_expire_days() -> timedelta:
    return timedelta(days=90)
