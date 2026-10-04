"""M5-10 风控 - 负责人 A

PRD 验收：**同一设备 / IP 异常行为触发人工审核**。

设计原则（刻意不选「静默拦截」）：
- 命中的订单**不直接拒绝**，而是打上 `review` 标记进入人工审核队列，
  同时向用户给出中文说明——避免误伤真实用户，也让运营可追溯。
- 规则数据化（`_RULES`），阈值集中一处，便于运营按实际数据调参。
- 每个事件落 `risk_events` 表，事后可审计、可申诉。

身份键统一使用 `core.context.owner_key_for_user` 的规范：`guest:<token>` / `user:<id>`。
注意不要混用 `User.id` 与 owner_key，否则「统计本账号订单数」会永远为 0。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Order, RiskEvent, User

# level: normal=仅记录；review=需人工审核（不阻断用户，但订单被标记）
LEVEL_NORMAL = "normal"
LEVEL_REVIEW = "review"

# 规则阈值（统一放这里，运营可按数据调整）
_RULES = {
    # 同一用户在 10 分钟内创建订单数 ≥ 5 → 疑似刷单
    "order_burst": {"window_minutes": 10, "threshold": 5, "level": LEVEL_REVIEW},
    # 同一用户在 24 小时内退款数 ≥ 3 → 疑似恶意退款
    "refund_abuse": {"window_minutes": 60 * 24, "threshold": 3, "level": LEVEL_REVIEW},
    # 同一 IP 在 10 分钟内出现的下单账号数 ≥ 5 → 疑似批量注册薅羊毛
    "multi_account_same_ip": {"window_minutes": 10, "threshold": 5, "level": LEVEL_REVIEW},
}

SIGNAL_LABELS = {
    "order_burst": "短时间内下单过于频繁",
    "refund_abuse": "近期退款次数偏多",
    "multi_account_same_ip": "同一网络下出现多个下单账号",
}

REVIEW_NOTICE = (
    "你的账户近期有异常操作，本单已进入人工审核，"
    "审核通常在 24 小时内完成。若为正常使用，我们会尽快放行，给你带来的不便请谅解。"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _since(minutes: int) -> datetime:
    return _now() - timedelta(minutes=minutes)


async def _resolve_user_id(db, owner_key: str) -> str | None:
    """规范 owner_key → User.id（下单/退款统计都挂在 users 表上）。"""
    if not owner_key:
        return None
    if owner_key.startswith("user:"):
        return owner_key.split(":", 1)[1]
    if owner_key.startswith("guest:"):
        token = owner_key.split(":", 1)[1]
        row = (
            await db.execute(select(User).where(User.guest_token == token))
        ).scalar_one_or_none()
        return row.id if row else None
    return None


async def _count_orders(db, owner_key: str, minutes: int) -> int:
    user_id = await _resolve_user_id(db, owner_key)
    if not user_id:
        return 0
    row = (
        await db.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.user_id == user_id, Order.created_at >= _since(minutes))
        )
    ).scalar_one()
    return int(row or 0)


async def _count_events(db, owner_key: str, signal: str, minutes: int) -> int:
    row = (
        await db.execute(
            select(func.count())
            .select_from(RiskEvent)
            .where(
                RiskEvent.owner_key == owner_key,
                RiskEvent.signal == signal,
                RiskEvent.created_at >= _since(minutes),
            )
        )
    ).scalar_one()
    return int(row or 0)


async def _distinct_accounts_for_ip(db, client_ip: str, minutes: int) -> int:
    if not client_ip:
        return 0
    rows = (
        await db.execute(
            select(func.distinct(RiskEvent.owner_key)).where(
                RiskEvent.owner_key.like(f"ip:{client_ip}:%"),
                RiskEvent.created_at >= _since(minutes),
            )
        )
    ).scalars().all()
    return len(rows)


async def record_event(
    db, owner_key: str, signal: str, level: str = LEVEL_NORMAL, detail: dict | None = None
) -> None:
    db.add(
        RiskEvent(
            id=str(uuid.uuid4()),
            owner_key=owner_key,
            signal=signal,
            level=level,
            detail=json.dumps(detail or {}, ensure_ascii=False),
        )
    )


async def evaluate_order_risk(db, owner_key: str, client_ip: str | None = None) -> str | None:
    """下单前的风控体检。命中返回 signal 标识（调用方据此打 risk_flag）。"""
    burst = _RULES["order_burst"]
    if await _count_orders(db, owner_key, burst["window_minutes"]) >= burst["threshold"]:
        await record_event(db, owner_key, "order_burst", burst["level"])
        return "order_burst"

    ip_rule = _RULES["multi_account_same_ip"]
    if client_ip:
        # 先按「IP + 账号」记账，再判断该 IP 下出现过的账号数
        await record_event(db, f"ip:{client_ip}:{owner_key}", "ip_seen", LEVEL_NORMAL)
        if (
            await _distinct_accounts_for_ip(db, client_ip, ip_rule["window_minutes"])
            >= ip_rule["threshold"]
        ):
            await record_event(db, owner_key, "multi_account_same_ip", ip_rule["level"])
            return "multi_account_same_ip"

    return None


async def evaluate_refund_risk(db, owner_key: str) -> str | None:
    rule = _RULES["refund_abuse"]
    if await _count_events(db, owner_key, "refund_done", rule["window_minutes"]) >= rule["threshold"]:
        await record_event(db, owner_key, "refund_abuse", rule["level"])
        return "refund_abuse"
    return None


def risk_payload(flag: str | None) -> dict:
    """给前端的风控说明（中文，透明不隐瞒）。"""
    if not flag:
        return {"flagged": False, "signal": None, "label": "", "notice": ""}
    return {
        "flagged": True,
        "signal": flag,
        "label": SIGNAL_LABELS.get(flag, "异常操作"),
        "notice": REVIEW_NOTICE,
    }


async def overview(db, owner_key: str) -> dict:
    """订单页/个人中心可查询自己的风控状态，避免「莫名被拦」的体验。"""
    rows = (
        await db.execute(
            select(RiskEvent)
            .where(RiskEvent.owner_key == owner_key, RiskEvent.level == LEVEL_REVIEW)
            .order_by(RiskEvent.created_at.desc())
            .limit(5)
        )
    ).scalars().all()
    return {
        "has_review": bool(rows),
        "items": [
            {
                "signal": r.signal,
                "label": SIGNAL_LABELS.get(r.signal, "异常操作"),
                "created_at": r.created_at.isoformat().replace("+00:00", "Z") if r.created_at else None,
            }
            for r in rows
        ],
        "notice": REVIEW_NOTICE if rows else "",
    }
