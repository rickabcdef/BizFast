"""V5.0 M4-07 转化漏斗（P0）。

漏斗步骤（严格按需求文档顺序）：
访问 → 开始诊断 → 完成诊断 → 点击付费 → 支付成功 → 下载交付物

数据来源：
- visit / diagnose_start / pay_click / download：FunnelEvent 埋点（前端在关键节点上报）；
- diagnose_done：优先真实 DiagnosisTask（status=ready），与埋点取较大值兜底；
- pay_success：真实订单（已支付及之后状态），保证漏斗口径与财务一致。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import DiagnosisTask, FunnelEvent, Order

logger = logging.getLogger(__name__)

STEPS = [
    ("visit", "访问"),
    ("diagnose_start", "开始诊断"),
    ("diagnose_done", "完成诊断"),
    ("pay_click", "点击付费"),
    ("pay_success", "支付成功"),
    ("download", "下载交付物"),
]
STEP_KEYS = [s for s, _ in STEPS]
STEP_LABELS = dict(STEPS)

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


async def track(db, owner_key: str | None, step: str, source: str | None = None) -> dict:
    """记录一次漏斗埋点（M5-04 分享动作埋点同源复用）。"""
    if step not in STEP_KEYS:
        # 未知步骤不报错，避免前端埋点升级导致主流程失败
        logger.debug("忽略未知漏斗步骤：%s", step)
        return {"ok": False}
    db.add(FunnelEvent(owner_key=owner_key, step=step, source=source))
    await db.commit()
    return {"ok": True}


async def _count_events(db, step: str, since: datetime) -> int:
    return int(
        (await db.execute(
            select(func.count(FunnelEvent.id)).where(
                FunnelEvent.step == step, FunnelEvent.created_at >= since
            )
        )).scalar_one() or 0
    )


async def funnel(db, period: str = "day") -> dict:
    """返回漏斗每一步的人数、转化率与流失率（异常流失自动标红）。"""
    days = PERIOD_DAYS.get(period, 1)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 埋点口径
    ev = {s: await _count_events(db, s, since) for s in STEP_KEYS}

    # 真实业务表兜底（保证漏斗不因埋点缺失而失真）
    diag_total = int(
        (await db.execute(
            select(func.count(DiagnosisTask.id)).where(DiagnosisTask.created_at >= since)
        )).scalar_one() or 0
    )
    diag_done = int(
        (await db.execute(
            select(func.count(DiagnosisTask.id)).where(
                DiagnosisTask.created_at >= since, DiagnosisTask.status == "ready"
            )
        )).scalar_one() or 0
    )
    pay_success = int(
        (await db.execute(
            select(func.count(Order.id)).where(
                Order.created_at >= since,
                Order.status.in_(["paid", "generating", "delivered", "refunded"]),
            )
        )).scalar_one() or 0
    )

    values = {
        "visit": ev["visit"],
        "diagnose_start": max(ev["diagnose_start"], diag_total),
        "diagnose_done": max(ev["diagnose_done"], diag_done),
        "pay_click": ev["pay_click"],
        "pay_success": max(ev["pay_success"], pay_success),
        "download": ev["download"],
    }

    rows = []
    top = values["visit"] or 0
    prev = None
    for key, label in STEPS:
        n = values[key]
        step_rate = round(n / top, 4) if top else 0.0
        prev_rate = round(n / prev, 4) if prev else None
        rows.append({
            "step": key,
            "label": label,
            "value": n,
            "rate_from_top": step_rate,
            "rate_from_prev": prev_rate,
            # 相邻步流失超过 70% 视为异常流失，标红提醒
            "drop_alert": bool(prev_rate is not None and prev_rate < 0.3),
        })
        if n:
            prev = n

    overall = round(values["pay_success"] / top, 4) if top else 0.0
    return {
        "period": period,
        "steps": rows,
        "overall_conversion": overall,
        "notice": (
            "存在异常流失环节，建议检查对应页面的引导与加载速度"
            if any(r["drop_alert"] for r in rows)
            else "各环节转化正常"
        ),
    }
