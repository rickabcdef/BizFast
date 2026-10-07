"""V5.0 第 8 章「运营自动化」：一个人也能跑起来。

三件事必须由系统自动完成，创始人只负责看：
1. **每日数据日报**（8.2）：每天 9 点生成昨日营收/订单/新增/退款/AI 成本/净现金流，
   落库 + 推送（推送失败不丢数据）。
2. **异常订单告警**（M2-04）：每 5 分钟扫描，已支付却迟迟未交付的订单立刻告警；
   同时做**主动查单兜底**（M2-01 / 第 10.2 节），回调缺失自动补单，绝不漏单；
   按 fingerprint 去重，不重复刷屏。
3. **会员到期提醒**（M0-03）：每天扫描，到期前 3 天内提醒一次续费。

设计原则：
- **先落库、再推送**。推送渠道（webhook）未配置时只落库 + 打日志，不抛错、不阻断。
- 所有扫描都是**幂等**的：重复执行不会产生重复记录。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AdminAlert, AiCostLog, DailyReport, Order, User

logger = logging.getLogger(__name__)

# 渠道费率（第 1 章：微信个人主体虚拟支付 Android 端 1%、iOS 端 12%）
# 日报按 Android 端 1% 估算通道费，保守且贴近多数用户场景。
CHANNEL_FEE_RATIO = 0.01


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _yuan(cents: int) -> str:
    return f"{cents / 100:.2f}"


# ---------------------------------------------------------------- 1. 每日数据日报
async def build_daily_report(db: AsyncSession, report_date: str | None = None) -> dict:
    """生成（并落库）某一天的日报。默认统计「昨天」。

    report_date 为统计日 YYYY-MM-DD；幂等：同一天重复调用会更新既有记录。
    """
    today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = today_start - timedelta(days=1)
    day_end = today_start
    stat_date = report_date or day_start.strftime("%Y-%m-%d")

    # 昨日营收 / 订单（口径与后台看板一致：paid/generating/delivered/refunded 计入营收）
    paid_rows = (
        await db.execute(
            select(Order).where(
                Order.paid_at >= day_start,
                Order.paid_at < day_end,
                Order.status.in_(["paid", "generating", "delivered", "refunded"]),
            )
        )
    ).scalars().all()
    revenue_cents = sum(o.amount for o in paid_rows)
    order_count = len(paid_rows)

    # 昨日退款
    refund_rows = (
        await db.execute(
            select(Order).where(
                Order.status == "refunded",
                Order.refunded_at >= day_start,
                Order.refunded_at < day_end,
            )
        )
    ).scalars().all()
    refund_cents = sum(o.amount for o in refund_rows)
    refund_count = len(refund_rows)

    # 昨日新增用户
    new_users = int(
        (
            await db.execute(
                select(func.count(User.id)).where(
                    User.created_at >= day_start, User.created_at < day_end
                )
            )
        ).scalar()
        or 0
    )

    # 昨日 AI 成本
    ai_cost_cents = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(AiCostLog.cost_cents), 0)).where(
                    AiCostLog.created_at >= day_start, AiCostLog.created_at < day_end
                )
            )
        ).scalar()
        or 0
    )

    channel_fee_cents = int(round(revenue_cents * CHANNEL_FEE_RATIO))
    net_cash_cents = revenue_cents - refund_cents - ai_cost_cents - channel_fee_cents

    content = (
        f"【生意快启 · {stat_date} 数据日报】\n"
        f"营收：¥{_yuan(revenue_cents)}（{order_count} 单）\n"
        f"新增用户：{new_users} 人\n"
        f"退款：¥{_yuan(refund_cents)}（{refund_count} 单）\n"
        f"AI 成本：¥{_yuan(ai_cost_cents)}\n"
        f"通道费预估(1%)：¥{_yuan(channel_fee_cents)}\n"
        f"净现金流：¥{_yuan(net_cash_cents)}\n"
        f"（数据延迟 ≤ 5 分钟）"
    )

    row = (
        await db.execute(select(DailyReport).where(DailyReport.report_date == stat_date))
    ).scalar_one_or_none()
    if row is None:
        row = DailyReport(id=str(uuid.uuid4()), report_date=stat_date)
        db.add(row)
    row.revenue_cents = revenue_cents
    row.order_count = order_count
    row.new_users = new_users
    row.refund_cents = refund_cents
    row.refund_count = refund_count
    row.ai_cost_cents = ai_cost_cents
    row.net_cash_cents = net_cash_cents
    row.content = content
    await db.commit()
    await db.refresh(row)
    return daily_report_payload(row, channel_fee_cents=channel_fee_cents)


def daily_report_payload(row: DailyReport, channel_fee_cents: int | None = None) -> dict:
    if channel_fee_cents is None:
        channel_fee_cents = int(round(row.revenue_cents * CHANNEL_FEE_RATIO))
    return {
        "id": row.id,
        "report_date": row.report_date,
        "revenue_cents": row.revenue_cents,
        "revenue_label": _yuan(row.revenue_cents),
        "order_count": row.order_count,
        "new_users": row.new_users,
        "refund_cents": row.refund_cents,
        "refund_label": _yuan(row.refund_cents),
        "refund_count": row.refund_count,
        "ai_cost_cents": row.ai_cost_cents,
        "ai_cost_label": _yuan(row.ai_cost_cents),
        "channel_fee_cents": channel_fee_cents,
        "channel_fee_label": _yuan(channel_fee_cents),
        "net_cash_cents": row.net_cash_cents,
        "net_cash_label": _yuan(row.net_cash_cents),
        "push_status": row.push_status,
        "pushed_at": row.pushed_at.isoformat() if row.pushed_at else None,
        "content": row.content,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def push_daily_report(db: AsyncSession, report: dict) -> str:
    """推送日报：优先 webhook，未配置则只落库（push_status=pending）。"""
    status = await _push_text(report["content"], title="生意快启数据日报")
    row = (
        await db.execute(select(DailyReport).where(DailyReport.id == report["id"]))
    ).scalar_one_or_none()
    if row is not None:
        row.push_status = status
        if status == "sent":
            row.pushed_at = _utcnow()
        await db.commit()
    return status


async def list_daily_reports(db: AsyncSession, limit: int = 30) -> list[dict]:
    rows = (
        await db.execute(
            select(DailyReport).order_by(DailyReport.report_date.desc()).limit(limit)
        )
    ).scalars().all()
    return [daily_report_payload(r) for r in rows]


async def get_daily_report(db: AsyncSession, report_date: str) -> dict | None:
    row = (
        await db.execute(select(DailyReport).where(DailyReport.report_date == report_date))
    ).scalar_one_or_none()
    return daily_report_payload(row) if row else None


async def run_daily_report_job(db: AsyncSession) -> dict:
    """定时任务入口：生成昨日日报并推送。"""
    report = await build_daily_report(db)
    status = await push_daily_report(db, report)
    report["push_status"] = status
    logger.info("每日数据日报已生成：%s（推送 %s）", report["report_date"], status)
    return report


# ---------------------------------------------------------------- 2. 异常订单告警
def _alert_brief(alert: AdminAlert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "level": alert.level,
        "title": alert.title,
        "content": alert.content,
        "related_type": alert.related_type,
        "related_id": alert.related_id,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


async def raise_alert(
    db: AsyncSession,
    *,
    alert_type: str,
    title: str,
    content: str = "",
    level: str = "warning",
    related_type: str | None = None,
    related_id: str | None = None,
    fingerprint: str | None = None,
    push: bool = True,
) -> dict | None:
    """通用告警写入（M2-04）。

    供「即时类」事件使用：事件当下就写告警并推送，不必等 5 分钟轮询任务，
    从而满足「异常 5 分钟内后台可见」的验收要求（例如已下载订单的退款申请）。
    `fingerprint` 相同视为同一条告警，不重复生成、不重复推送。
    """
    fp = fingerprint or f"{alert_type}:{related_id or uuid.uuid4().hex[:8]}"
    exists = (
        await db.execute(select(AdminAlert).where(AdminAlert.fingerprint == fp))
    ).scalar_one_or_none()
    if exists is not None:
        return None

    alert = AdminAlert(
        id=str(uuid.uuid4()),
        alert_type=alert_type,
        level=level,
        title=title,
        content=content,
        related_type=related_type,
        related_id=related_id,
        fingerprint=fp,
    )
    db.add(alert)
    await db.flush()
    brief = _alert_brief(alert)
    await db.commit()

    if push:
        try:
            await _push_text(content or title, title=title)
        except Exception as exc:  # 推送失败不影响业务主流程
            logger.warning("告警推送失败：%s", exc)
    logger.info("后台告警：%s", title)
    return brief


async def detect_abnormal_orders(db: AsyncSession) -> list[dict]:
    """扫描异常订单（M2-04）。已支付超过阈值仍未交付 → 异常。

    返回本次**新增**的告警列表（已存在的不重复生成）。
    """
    threshold_hours = int(getattr(settings, "order_abnormal_hours", 2) or 2)
    now = _utcnow()
    orders = (
        await db.execute(select(Order).where(Order.status.in_(["paid", "generating"])))
    ).scalars().all()

    created: list[dict] = []
    for order in orders:
        paid_at = _naive(order.paid_at)
        if paid_at is None:
            continue
        hours = (now - paid_at).total_seconds() / 3600
        if hours < threshold_hours:
            continue

        fingerprint = f"order_abnormal:{order.id}"
        exists = (
            await db.execute(
                select(AdminAlert).where(AdminAlert.fingerprint == fingerprint)
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue  # 已告警过，不重复刷屏

        title = f"异常订单：{order.id[:8]} 已支付 {hours:.1f} 小时未交付"
        content = (
            f"订单 {order.id}（{order.plan}，金额 ¥{_yuan(order.amount)}）"
            f"于 {paid_at.strftime('%Y-%m-%d %H:%M')} 支付，当前状态 {order.status}，"
            f"超过 {threshold_hours} 小时仍未交付，请到「订单管理」一键处理。"
        )
        alert = AdminAlert(
            id=str(uuid.uuid4()),
            alert_type="order_abnormal",
            level="danger",
            title=title,
            content=content,
            related_type="order",
            related_id=order.id,
            fingerprint=fingerprint,
        )
        db.add(alert)
        created.append(alert)

    if created:
        await db.commit()
        for a in created:
            await _push_text(a.content, title=a.title)
            logger.warning("异常订单告警：%s", a.title)
    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "level": a.level,
            "title": a.title,
            "content": a.content,
            "related_type": a.related_type,
            "related_id": a.related_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in created
    ]


async def detect_payment_anomalies(db: AsyncSession) -> list[dict]:
    """M2-01 / M2-04（V5.0）：主动查单兜底 + 回调缺失 / 重复支付告警。

    1. **回调缺失**：待支付订单创建超过 order_callback_missing_minutes 仍未收到回调 →
       主动向渠道查单。渠道已扣款 → **自动补单**并告警（防漏单，用户不会付了钱拿不到货）；
       渠道查不到 → 告警交人工核对。
    2. **重复支付**：同一用户在窗口内出现 ≥2 笔已支付订单 → 告警（可能重复扣款，需退款）。
    """
    from app.services import payment as payment_service

    created: list[dict] = []
    now = _utcnow()
    miss_minutes = int(getattr(settings, "order_callback_missing_minutes", 15) or 15)

    # ---- 1) 回调缺失 → 主动查单补单 ----
    pendings = (
        await db.execute(select(Order).where(Order.status == "pending"))
    ).scalars().all()
    for order in pendings:
        created_at = _naive(order.created_at)
        if created_at is None:
            continue
        age_minutes = (now - created_at).total_seconds() / 60
        if age_minutes < miss_minutes:
            continue
        if payment_service._is_expired(order):
            continue  # 超时未支付的订单由主动查单关单，不算异常

        recovered = False
        try:
            recovered = await payment_service.recover_pending_order(db, order)
        except Exception as exc:  # 查单失败不阻断扫描
            logger.warning("主动查单补单失败：%s", exc)

        fingerprint = f"callback_missing:{order.id}"
        exists = (
            await db.execute(select(AdminAlert).where(AdminAlert.fingerprint == fingerprint))
        ).scalar_one_or_none()
        if exists is not None:
            continue

        if recovered:
            level = "warning"
            title = f"回调缺失（已自动补单）：{order.id[:8]}"
            content = (
                f"订单 {order.id}（{order.plan}，金额 ¥{_yuan(order.amount)}）创建 "
                f"{age_minutes:.0f} 分钟未收到渠道回调，主动查单确认渠道**已扣款**，"
                f"系统已自动补单并发放权益（用户无感知，无需人工介入）。"
            )
        else:
            level = "danger"
            title = f"回调缺失待核对：{order.id[:8]}"
            content = (
                f"订单 {order.id}（{order.plan}，金额 ¥{_yuan(order.amount)}）创建 "
                f"{age_minutes:.0f} 分钟仍未支付且渠道查不到已付记录。若用户反馈已扣款，"
                f"请到「订单管理」人工核对后手动补单。"
            )
        alert = AdminAlert(
            id=str(uuid.uuid4()),
            alert_type="callback_missing",
            level=level,
            title=title,
            content=content,
            related_type="order",
            related_id=order.id,
            fingerprint=fingerprint,
        )
        db.add(alert)
        created.append(alert)

    # ---- 2) 重复支付 ----
    window = int(getattr(settings, "duplicate_payment_window_minutes", 10) or 10)
    since = now - timedelta(minutes=window)
    paid_rows = (
        await db.execute(
            select(Order).where(
                Order.status.in_(["paid", "generating", "delivered"]),
                Order.paid_at.is_not(None),
            )
        )
    ).scalars().all()
    by_user: dict[str, list[Order]] = {}
    for order in paid_rows:
        paid_at = _naive(order.paid_at)
        if paid_at is None or paid_at < since:
            continue
        by_user.setdefault(order.user_id, []).append(order)

    for user_id, orders in by_user.items():
        if len(orders) < 2:
            continue
        anchor = sorted(o.id for o in orders)[0]
        fingerprint = f"duplicate_payment:{user_id}:{anchor}"
        exists = (
            await db.execute(select(AdminAlert).where(AdminAlert.fingerprint == fingerprint))
        ).scalar_one_or_none()
        if exists is not None:
            continue
        ids = "、".join(o.id[:8] for o in orders)
        total = sum(o.amount or 0 for o in orders)
        alert = AdminAlert(
            id=str(uuid.uuid4()),
            alert_type="duplicate_payment",
            level="danger",
            title=f"疑似重复支付：用户 {user_id[:8]} 连续 {len(orders)} 笔",
            content=(
                f"用户 {user_id} 在 {window} 分钟内产生 {len(orders)} 笔已支付订单"
                f"（{ids}），合计 ¥{_yuan(total)}。请核对是否为重复扣款，如是请及时退款。"
            ),
            related_type="user",
            related_id=user_id,
            fingerprint=fingerprint,
        )
        db.add(alert)
        created.append(alert)

    if created:
        await db.commit()
        for a in created:
            await _push_text(a.content, title=a.title)
            logger.warning("支付异常告警：%s", a.title)
    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "level": a.level,
            "title": a.title,
            "content": a.content,
            "related_type": a.related_type,
            "related_id": a.related_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in created
    ]


async def detect_cost_overrun(db: AsyncSession) -> list[dict]:
    """成本占收入比超阈值（第 7.1：> 25%）时写一条告警（按天去重）。"""
    from app.services import ai_cost

    monitor = await ai_cost.cost_monitor(db)
    if not monitor.get("alert"):
        return []
    day = _utcnow().strftime("%Y-%m-%d")
    fingerprint = f"cost_overrun:{day}"
    exists = (
        await db.execute(select(AdminAlert).where(AdminAlert.fingerprint == fingerprint))
    ).scalar_one_or_none()
    if exists is not None:
        return []
    alert = AdminAlert(
        id=str(uuid.uuid4()),
        alert_type="cost_overrun",
        level="warning",
        title=f"AI 成本占收入比超过 {int(monitor.get('alert_ratio', 0.25) * 100)}%",
        content=monitor.get("notice") or "请检查模型路由 / 缓存 / 模板比例",
        related_type="cost",
        related_id=day,
        fingerprint=fingerprint,
    )
    db.add(alert)
    await db.commit()
    await _push_text(alert.content, title=alert.title)
    return [{"id": alert.id, "alert_type": alert.alert_type, "level": alert.level, "title": alert.title}]


async def list_alerts(db: AsyncSession, limit: int = 50, unread_only: bool = False) -> dict:
    stmt = select(AdminAlert)
    if unread_only:
        stmt = stmt.where(AdminAlert.is_read.is_(False))
    rows = (
        await db.execute(stmt.order_by(AdminAlert.created_at.desc()).limit(limit))
    ).scalars().all()
    unread = int(
        (
            await db.execute(
                select(func.count(AdminAlert.id)).where(AdminAlert.is_read.is_(False))
            )
        ).scalar()
        or 0
    )
    return {
        "items": [
            {
                "id": r.id,
                "alertType": r.alert_type,
                "level": r.level,
                "title": r.title,
                "content": r.content,
                "relatedType": r.related_type,
                "relatedId": r.related_id,
                "isRead": r.is_read,
                "createdAt": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            }
            for r in rows
        ],
        "unread": unread,
    }


async def mark_alert_read(db: AsyncSession, alert_id: str | None = None) -> int:
    stmt = select(AdminAlert)
    if alert_id:
        stmt = stmt.where(AdminAlert.id == alert_id)
    else:
        stmt = stmt.where(AdminAlert.is_read.is_(False))
    rows = (await db.execute(stmt)).scalars().all()
    for r in rows:
        r.is_read = True
    if rows:
        await db.commit()
    return len(rows)


async def run_alert_scan_job(db: AsyncSession) -> dict:
    """定时任务入口：扫描异常订单 + 支付异常（回调缺失 / 重复支付）+ 成本超限。"""
    orders = await detect_abnormal_orders(db)
    payments = await detect_payment_anomalies(db)
    costs = await detect_cost_overrun(db)
    return {"orders": len(orders), "payments": len(payments), "costs": len(costs)}


# ---------------------------------------------------------------- 3. 会员到期提醒
async def notify_expiring_members(db: AsyncSession) -> int:
    """M0-03（V5.0）：到期前 3 天 / 1 天自动提醒续费。返回本次提醒人数。

    注意：提醒对象是**所有月/年会员**，不限于已开启自动续费的用户 ——
    未开启自动续费的人同样会到期，不提醒就等于静默流失。
    """
    from app.services import payment as payment_service

    users = (
        await db.execute(
            select(User).where(
                User.plan.in_(["month", "year"]),
                User.plan_expire_at.is_not(None),
            )
        )
    ).scalars().all()

    sent = 0
    for user in users:
        try:
            if await payment_service.maybe_notify_renewal(db, user):
                sent += 1
        except Exception as exc:  # 单个用户失败不影响其它用户
            logger.warning("会员到期提醒失败：user=%s err=%s", user.id, exc)
    if sent:
        await db.commit()
        logger.info("会员到期提醒已发送 %s 人", sent)
    return sent


# ---------------------------------------------------------------- 推送通道
async def _push_text(content: str, title: str = "") -> str:
    """把文本推送到创始人。返回 sent / pending / failed。

    未配置 webhook（默认）时返回 pending —— 数据已落库，后台随时可查，
    符合「零成本、不阻断」原则。配置后支持企业微信 / 飞书等机器人 webhook。
    """
    url = (getattr(settings, "admin_alert_webhook", "") or "").strip()
    if not url:
        return "pending"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"msgtype": "text", "text": {"content": content}})
        return "sent" if resp.status_code < 300 else "failed"
    except Exception as exc:
        logger.warning("推送失败（已落库不丢数据）：%s", exc)
        return "failed"
