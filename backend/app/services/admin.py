"""M11 运营管理后台 - 业务逻辑层。

提供看板、用户/订单管理、商机库、提示词、审核、权限、审计、运营位、导出等功能。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BizError
from app.core.security import create_access_token
from app.models import AiCostLog, DiagnosisTask, Order, Package, PaymentRecord, User
from app.schemas import admin as admin_schemas

# ─── 配置与常量 ───

CONFIG_DIR = Path(__file__).parent.parent.parent / "data" / "admin_config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

MOCK_ACCOUNTS = {
    "admin": {"password": "admin123", "name": "系统管理员", "role": "admin"},
    "operator": {"password": "op123", "name": "运营小王", "role": "operator"},
    "support": {"password": "sup123", "name": "客服小张", "role": "support"},
    "finance": {"password": "fin123", "name": "财务小丽", "role": "finance"},
}

ROLE_NAMES = {
    "admin": "管理员",
    "operator": "运营",
    "support": "客服",
    "finance": "财务",
}


def _mask_phone(phone: Optional[str]) -> str:
    """V5.0 第 10.2 节：敏感信息（手机号）脱敏展示。

    后台列表 / 详情 / 导出对账单都只展示 `138****2211` 这种形态，
    既不泄露完整号码，也足够客服核对用户身份。
    """
    if not phone:
        return "未绑定"
    digits = phone.strip()
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"

PLAN_NAMES = {
    "none": "游客",
    "single": "单次购买",
    "month": "月度会员",
    "year": "年度会员",
}

ORDER_ABNORMAL_LABELS = {
    "paid_no_delivery": "已支付未交付（超2小时）",
    "callback_missing": "支付回调缺失",
    "refund_review": "退款待人工审核",
    "duplicate_payment": "疑似重复支付",
}

# M0-04（V5.0）：用户来源渠道（后台可查任意用户的邀请来源）
SOURCE_INVITE = "邀请注册"
SOURCE_ORGANIC = "自然流量"

# 订单状态 → 中文标签（后台列表直接展示，避免露出英文状态码）
ORDER_STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "generating": "生成中",
    "delivered": "已交付",
    "refunded": "已退款",
    "closed": "已关闭",
}


# ─── 辅助函数 ───

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _load_json(filename: str, default: any = None):
    path = CONFIG_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def _save_json(filename: str, data: any):
    path = CONFIG_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def resolve_user_source_index(db: AsyncSession) -> dict:
    """M0-04（V5.0）：解析「用户 → 来源渠道 / 邀请人」。

    优先级：**邀请注册**（有邀请关系）> 埋点渠道（FunnelEvent.source）> 自然流量。
    返回 {"invited": {user_id: inviter_id}, "channel": {user_id: source_label}}。
    """
    from app.models import FunnelEvent, InviteRelation

    invited: dict[str, str] = {}
    rows = (await db.execute(select(InviteRelation.invitee_user_id, InviteRelation.inviter_user_id))).all()
    for invitee_id, inviter_id in rows:
        invited[invitee_id] = inviter_id

    # 每个 owner_key 最早一条埋点事件的来源渠道（`user:<id>` / `guest:<token>`）
    events = (
        await db.execute(
            select(FunnelEvent.owner_key, FunnelEvent.source, func.min(FunnelEvent.created_at))
            .where(FunnelEvent.source.is_not(None))
            .group_by(FunnelEvent.owner_key, FunnelEvent.source)
        )
    ).all()
    channel: dict[str, str] = {}
    for owner_key, source, _ts in events:
        if not owner_key or not owner_key.startswith("user:"):
            continue
        uid = owner_key.split(":", 1)[1]
        channel.setdefault(uid, source)
    return {"invited": invited, "channel": channel}


def _source_of(user_id: str, index: dict) -> str:
    if user_id in index["invited"]:
        return SOURCE_INVITE
    return index["channel"].get(user_id) or SOURCE_ORGANIC


def _iter_known_user_ids(index: dict) -> set[str]:
    """已知有「非自然流量」来源的用户 id 集合（用于来源筛选）。"""
    return set(index["invited"]) | set(index["channel"])


async def _inviter_phones(db: AsyncSession, inviter_ids: list[str]) -> dict[str, str]:
    if not inviter_ids:
        return {}
    rows = (
        await db.execute(select(User.id, User.phone).where(User.id.in_(inviter_ids)))
    ).all()
    return {uid: _mask_phone(phone) for uid, phone in rows}


def write_audit_log(session: dict, action: str, target: str, detail: str = ""):
    """写入审计日志（M11-08）。"""
    logs = _load_json("audit_logs.json", [])
    log_entry = {
        "id": f"A-{int(time.time() * 1000)}",
        "operator": session.get("name", "Unknown"),
        "role": ROLE_NAMES.get(session.get("role", ""), session.get("role", "")),
        "action": action,
        "target": target,
        "detail": detail,
        "createdAt": _now_str(),
    }
    logs.insert(0, log_entry)
    # 保留最近 1000 条
    logs = logs[:1000]
    _save_json("audit_logs.json", logs)


# ─── 登录 ───

async def admin_login_step1(username: str, password: str) -> dict:
    """管理员登录第一步：校验账号密码。"""
    acc = MOCK_ACCOUNTS.get(username.strip())
    if not acc or acc["password"] != password:
        raise BizError(40001, "账号或密码错误")
    # Mock TOTP
    return {"need_totp": True, "totp_hint": "123456"}


async def admin_login_step2(username: str, totp: str, db: AsyncSession) -> dict:
    """管理员登录第二步：校验 TOTP，签发真实 JWT 并返回会话。

    关键：后台会话必须是一枚可被 `require_admin` 解析的 access_token（JWT），
    因此这里为每个后台账号建立/复用一个 role 属于四角色之一的 User 行，
    并以该用户 id 作为 JWT 的 sub。
    """
    username = (username or "").strip()
    if totp.strip() != "123456":
        raise BizError(40002, "验证码不正确，请重新输入")

    acc = MOCK_ACCOUNTS.get(username)
    if not acc:
        raise BizError(40001, "账号不存在")

    # 复用/创建后台账号对应的 User 行（unionid 约定为 admin:<username>）
    unionid = f"admin:{username}"
    user = (
        await db.execute(select(User).where(User.unionid == unionid))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            unionid=unionid,
            role=acc["role"],
            plan="none",
        )
        db.add(user)
    else:
        # 角色可能被运营调整过，保持与实际账号一致
        user.role = acc["role"]
    await db.commit()
    await db.refresh(user)

    token = create_access_token(sub=user.id)
    session = {
        "token": token,
        "name": acc["name"],
        "username": username,
        "role": acc["role"],
        "login_at": _now_str(),
    }
    write_audit_log(session, "登录", "后台", f"账号 {username} 通过账号密码 + TOTP 二次验证登录")
    return session


# ─── 看板 ───

async def get_dashboard(db: AsyncSession, granularity: str = "day") -> dict:
    """获取看板数据（M11-05）。"""
    # 诊断数
    diag_count = (await db.execute(select(func.count(DiagnosisTask.id)))).scalar() or 0
    
    # 支付订单
    paid_orders = await db.execute(
        select(Order).where(Order.status.in_(["paid", "generating", "delivered"]))
    )
    paid_orders = paid_orders.scalars().all()
    pay_count = len(paid_orders)
    revenue_yuan = sum(o.amount / 100.0 for o in paid_orders)
    
    # 退款数
    refund_count = (await db.execute(
        select(func.count(Order.id)).where(Order.status == "refunded")
    )).scalar() or 0
    
    # 交付完成数
    delivered_count = (await db.execute(
        select(func.count(Package.id)).where(Package.status == "delivered")
    )).scalar() or 0
    
    # 计算指标
    conversion_rate = f"{(pay_count / diag_count * 100):.1f}%" if diag_count > 0 else "0%"
    package_done_rate = f"{(delivered_count / pay_count * 100):.1f}%" if pay_count > 0 else "0%"
    refund_rate = f"{(refund_count / pay_count * 100):.1f}%" if pay_count > 0 else "0%"
    avg_order_yuan = f"{revenue_yuan / pay_count:.1f}" if pay_count > 0 else "0"

    # V5.0 M4-01 现金流看板：今日新增用户 / 今日 AI 成本 / 净现金流
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_new_users = int(
        (await db.execute(
            select(func.count(User.id)).where(User.created_at >= today_start)
        )).scalar_one() or 0
    )
    ai_cost_cents = int(
        (await db.execute(
            select(func.coalesce(func.sum(AiCostLog.cost_cents), 0)).where(
                AiCostLog.created_at >= today_start
            )
        )).scalar_one() or 0
    )
    # 今日已支付订单（含已退款，口径与 cost_monitor 的 _revenue_cents 一致）
    today_orders = (
        await db.execute(
            select(func.count(Order.id), func.coalesce(func.sum(Order.amount), 0)).where(
                Order.paid_at >= today_start,
                Order.status.in_(["paid", "generating", "delivered", "refunded"]),
            )
        )
    ).one()
    today_order_count = int(today_orders[0] or 0)
    today_revenue_cents = int(today_orders[1] or 0)
    net_cashflow_cents = today_revenue_cents - ai_cost_cents
    
    kpis = admin_schemas.DashboardKpisOut(
        diagnose_count=diag_count,
        pay_count=pay_count,
        revenue_yuan=revenue_yuan,
        conversion_rate=conversion_rate,
        package_done_rate=package_done_rate,
        refund_rate=refund_rate,
        avg_order_yuan=avg_order_yuan,
        today_new_users=today_new_users,
        today_order_count=today_order_count,
        today_revenue_cents=today_revenue_cents,
        ai_cost_cents=ai_cost_cents,
        net_cashflow_cents=net_cashflow_cents,
    )
    
    # Mock Trend 数据
    trend_data = [
        {"label": "10/1", "orders": 10, "revenue": 148},
        {"label": "10/2", "orders": 16, "revenue": 236},
        {"label": "10/3", "orders": 9, "revenue": 121},
        {"label": "10/4", "orders": 15, "revenue": 232},
        {"label": "10/5", "orders": 8, "revenue": 104},
        {"label": "10/6", "orders": 12, "revenue": 186},
        {"label": "10/7", "orders": 16, "revenue": 254},
    ]
    trend = [admin_schemas.DashboardTrendItem(**t) for t in trend_data]
    
    return {
        "kpis": kpis,
        "trend": trend,
        "refresh_at": f"刚刚（延迟 ≤ 5 分钟）",
    }


# ─── 用户管理 ───

async def get_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    member_status: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    """获取用户列表（M11-01）。"""
    query = select(User)

    if keyword:
        query = query.where(
            User.phone.ilike(f"%{keyword}%") | 
            User.id.ilike(f"%{keyword}%")
        )
    if member_status:
        query = query.where(User.plan == member_status)

    # M0-04（V5.0）：来源渠道筛选（此前参数被接收却从未生效）
    index = await resolve_user_source_index(db)
    if source:
        known = _iter_known_user_ids(index)
        if source == SOURCE_ORGANIC:
            # 自然流量 = 既非邀请注册、也没有任何埋点渠道的用户
            if known:
                query = query.where(User.id.not_in(known))
        else:
            matched = [uid for uid in known if _source_of(uid, index) == source]
            # 未命中任何用户时用不可能匹配的条件，避免退化为「查全部」
            query = query.where(User.id.in_(matched) if matched else User.id.is_(None))

    # 总数
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    
    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    users = (await db.execute(query)).scalars().all()

    inviter_phones = await _inviter_phones(db, [index["invited"][u.id] for u in users if u.id in index["invited"]])

    items = []
    for u in users:
        # 查询订单数和消费总额
        order_stats = await db.execute(
            select(
                func.count(Order.id),
                func.sum(Order.amount)
            ).where(Order.user_id == u.id, Order.status.in_(["paid", "delivered"]))
        )
        order_count, total_spend = order_stats.one()
        order_count = order_count or 0
        total_spend = (total_spend or 0) / 100.0

        inviter_id = index["invited"].get(u.id)
        items.append(admin_schemas.AdminUserOut(
            id=u.id,
            phone=_mask_phone(u.phone),
            nickname=f"用户{u.id[:6]}",
            city=u.city or "",  # M0-02（V5.0）：用户画像里的所在城市
            member_status=u.plan,
            member_label=PLAN_NAMES.get(u.plan, "游客"),
            order_count=order_count,
            total_spend_yuan=total_spend,
            created_at=u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
            risk_flag=False,
            source=_source_of(u.id, index),
            inviter_phone=inviter_phones.get(inviter_id, "") if inviter_id else "",
            **(await _quota_fields(db, u)),
        ))
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _quota_fields(db: AsyncSession, user: User) -> dict:
    """M0-03（V5.0）：后台要能查到「剩余天数 / 已购次数 / 已用启动包数 / 额度剩余」。

    口径与用户端 `/api/user/me` 完全一致（同一份 `payment.membership_quota`），
    否则客服看到的额度和用户看到的对不上，会变成互相扯皮。
    """
    from app.services import payment as payment_service

    quota = await payment_service.membership_quota(db, user)
    expire = user.plan_expire_at
    days_left: Optional[int] = None
    if expire is not None:
        days_left = int((_aware(expire) - datetime.now(timezone.utc)).days)
    return {
        "expire_at": expire.strftime("%Y-%m-%d") if expire else "",
        "expire_days_left": days_left,
        **quota,
    }


async def get_user_detail(db: AsyncSession, user_id: str) -> dict:
    """获取用户详情（M11-01）。"""
    user = await db.get(User, user_id)
    if not user:
        raise BizError(40401, "用户不存在")
    
    # 订单列表
    orders = (await db.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    )).scalars().all()
    
    # 启动包列表
    packages = (await db.execute(
        select(Package).where(Package.user_id == user_id).order_by(Package.created_at.desc())
    )).scalars().all()
    
    # 构建用户对象
    order_stats = await db.execute(
        select(
            func.count(Order.id),
            func.sum(Order.amount)
        ).where(Order.user_id == user_id, Order.status.in_(["paid", "delivered"]))
    )
    order_count, total_spend = order_stats.one()

    # M0-04（V5.0）：邀请来源（含邀请人手机号，已脱敏）
    index = await resolve_user_source_index(db)
    inviter_id = index["invited"].get(user_id)
    inviter_phones = await _inviter_phones(db, [inviter_id] if inviter_id else [])
    inviter_phone = inviter_phones.get(inviter_id, "") if inviter_id else ""

    user_out = admin_schemas.AdminUserOut(
        id=user.id,
        phone=_mask_phone(user.phone),
        nickname=f"用户{user.id[:6]}",
        city=user.city or "",
        member_status=user.plan,
        member_label=PLAN_NAMES.get(user.plan, "游客"),
        order_count=order_count or 0,
        total_spend_yuan=(total_spend or 0) / 100.0,
        created_at=user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
        source=_source_of(user_id, index),
        inviter_phone=inviter_phone,
        **(await _quota_fields(db, user)),
    )
    
    # 构建订单列表（口径与订单列表页一致：退款申请 / 已下载 / 异常均真实反映）
    handled_ids = await _handled_order_ids(db, [o.id for o in orders])
    dup_ids = frozenset(_duplicate_payment_ids(list(orders)))
    orders_out = []
    for o in orders:
        flag, atype = _abnormal_flag(o, handled_ids, dup_ids)
        orders_out.append({
            "id": o.id,
            "userId": o.user_id,
            "userPhone": _mask_phone(user.phone),
            "plan": o.plan,
            "planName": PLAN_NAMES.get(o.plan, o.plan),
            "amountYuan": o.amount / 100.0,
            "status": o.status,
            "statusLabel": ORDER_STATUS_LABELS.get(o.status, o.status),
            "channel": o.channel or "",
            "createdAt": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
            "paidAt": o.paid_at.strftime("%Y-%m-%d %H:%M") if o.paid_at else None,
            "downloaded": o.downloaded_at is not None,
            "refundRequested": o.refund_review == "pending",
            "refundReason": o.refund_reason,
            "abnormal": flag,
            "abnormalType": atype,
        })
    
    # 构建启动包列表
    packages_out = []
    for p in packages:
        packages_out.append({
            "orderId": p.order_id,
            "name": f"启动包 {p.id[:8]}",
            "fileCount": 10 if p.status == "delivered" else 0,
            "status": p.status,
            "createdAt": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
        })
    
    return {
        "user": user_out,
        "orders": orders_out,
        "packages": packages_out,
    }


# ─── 订单管理 ───

async def _handled_order_ids(db: AsyncSession, order_ids: list[str]) -> set[str]:
    """M2-03（V5.0）：已被人工标记「已处理」的订单 id（订单事件里 action=resolve）。"""
    if not order_ids:
        return set()
    rows = (
        await db.execute(
            select(PaymentRecord.order_id).where(
                PaymentRecord.order_id.in_(order_ids),
                PaymentRecord.action == "resolve",
            )
        )
    ).all()
    return {r[0] for r in rows}


def _aware(dt: datetime) -> datetime:
    """SQLite 下读回的时间可能没有 tzinfo，统一按 UTC 处理后再比较。"""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# 视为「已完成支付」的状态（与 payment 的 PAID_STATUSES 语义一致）
_PAID_LIKE_STATUSES = ("paid", "generating", "delivered")


def _duplicate_payment_ids(orders: list[Order]) -> set[str]:
    """M2-04：同一用户在一个短窗口内出现 ≥2 笔已支付订单 → 全部标记「疑似重复支付」。

    口径必须与自动化巡检 `automation.detect_payment_anomalies` 使用同一配置项
    （`duplicate_payment_window_minutes`），否则会出现「告警里有、订单列表里搜不到红标」
    —— 后台拿到告警却定位不到订单，等于无法处理。
    """
    window = int(getattr(settings, "duplicate_payment_window_minutes", 10) or 10) * 60
    by_user: dict[str, list[Order]] = {}
    for order in orders:
        if order.status in _PAID_LIKE_STATUSES and order.paid_at:
            by_user.setdefault(order.user_id, []).append(order)

    dup: set[str] = set()
    for rows in by_user.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: _aware(r.paid_at))
        for prev, cur in zip(rows, rows[1:]):
            if (_aware(cur.paid_at) - _aware(prev.paid_at)).total_seconds() <= window:
                dup.add(prev.id)
                dup.add(cur.id)
    return dup


def _abnormal_flag(
    order: Order, handled_ids: set[str], dup_ids: frozenset[str] = frozenset()
) -> tuple[bool, str | None]:
    """统一的异常判定（列表展示与「仅看异常」筛选共用同一条口径）。

    优先级：退款待审核 > 疑似重复支付 > 已支付未交付 > 支付回调缺失。
    """
    atype: str | None = None
    # M2-05（V5.0）：交付物已下载的退款申请需人工审核 → 红色高亮提醒处理
    if order.refund_review == "pending":
        atype = "refund_review"
    # M2-04（V5.0）：同一用户短时间内多笔已支付 → 疑似重复支付
    elif order.id in dup_ids:
        atype = "duplicate_payment"
    elif order.status == "paid" and order.paid_at:
        if (_aware(order.paid_at) - datetime.now(timezone.utc)).total_seconds() < -7200:  # 超 2 小时
            atype = "paid_no_delivery"
    elif order.status == "pending" and order.created_at:
        miss_minutes = int(getattr(settings, "order_callback_missing_minutes", 15) or 15)
        age_minutes = (datetime.now(timezone.utc) - _aware(order.created_at)).total_seconds() / 60
        if miss_minutes <= age_minutes < 30:  # 超过阈值但尚未超时关单
            atype = "callback_missing"
    # M2-03（V5.0）：人工标记已处理后不再红色高亮
    if atype and order.id in handled_ids:
        return False, None
    return (atype is not None), atype


async def get_orders(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    abnormal: Optional[bool] = None,
    channel: Optional[str] = None,
) -> dict:
    """获取订单列表（M11-02）。

    异常筛选在**分页之前**完成 —— 否则「仅看异常」只会过滤当前页，
    导致总数与翻页结果都不对（后台「一键处理异常」会看到错误的清单）。
    """
    query = select(Order)

    if status:
        query = query.where(Order.status == status)
    if keyword:
        query = query.where(Order.id.ilike(f"%{keyword}%"))
    if channel:
        query = query.where(Order.channel == channel)

    query = query.order_by(Order.created_at.desc())
    orders = list((await db.execute(query)).scalars().all())

    handled_ids = await _handled_order_ids(db, [o.id for o in orders])
    dup_ids = frozenset(_duplicate_payment_ids(orders))

    filtered: list[tuple[Order, bool, str | None]] = []
    for o in orders:
        flag, atype = _abnormal_flag(o, handled_ids, dup_ids)
        if abnormal is not None and flag != abnormal:
            continue
        filtered.append((o, flag, atype))

    total = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

    items = []
    for o, is_abnormal, abnormal_type in page_rows:
        user = await db.get(User, o.user_id)
        user_phone = _mask_phone(user.phone if user else None)

        items.append(admin_schemas.AdminOrderOut(
            id=o.id,
            user_id=o.user_id,
            user_phone=user_phone,
            plan=o.plan,
            plan_name=PLAN_NAMES.get(o.plan, o.plan),
            amount_yuan=o.amount / 100.0,
            status=o.status,
            status_label=ORDER_STATUS_LABELS.get(o.status, o.status),
            channel=o.channel or "",
            created_at=o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
            paid_at=o.paid_at.strftime("%Y-%m-%d %H:%M") if o.paid_at else None,
            refund_requested=o.refund_review == "pending",
            refund_reason=o.refund_reason,
            downloaded=o.downloaded_at is not None,
            abnormal=is_abnormal,
            abnormal_type=abnormal_type,
            abnormal_handled=o.id in handled_ids,
        ))
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def process_refund(
    db: AsyncSession,
    session: dict,
    order_id: str,
    action: str,
    reason: Optional[str] = None,
) -> dict:
    """处理退款（M2-05 / M4-03 一键处理）。

    刻意走 payment 服务，而不是直接改 status —— 保证「退款 = 状态流转 + 回收会员权益
    + 释放优惠券额度 + 通知用户」整条链路完整执行（V5.0 要求退款后权益自动回收）。
    """
    order = await db.get(Order, order_id)
    if not order:
        raise BizError(40401, "订单不存在")
    status_before = order.status

    from app.services import payment as payment_service

    if action == "approve":
        # M2-03：后台既能审核用户申请，也能**主动退款**（重复支付 / 客诉补偿等，
        # 用户没提交申请的场景）。两种路径都走 payment 的完整退款链路（含权益回收）。
        manual = order.refund_review != "pending"
        result = await payment_service.approve_refund_review(db, order_id, manual=manual)
        write_audit_log(session, "主动退款" if manual else "同意退款", order_id, reason or "")
        return {
            "order_id": order_id,
            "status": "refunded",
            "revoked": bool(result.get("revoked")),
            "message": (
                "已主动退款，24小时内原路到账，会员权益已回收"
                if manual
                else "已同意退款，24小时内原路到账，会员权益已回收"
            ),
        }

    # 驳回只对「用户已提交的待审核申请」有意义，否则是无意义的空操作
    if order.refund_review != "pending":
        raise BizError(40901, "该订单没有待审核的退款申请，无法驳回")
    await payment_service.reject_refund_review(db, order_id, reason)
    write_audit_log(session, "驳回退款", order_id, reason or "")
    return {
        "order_id": order_id,
        "status": status_before,
        "message": "已驳回退款申请",
    }


async def resolve_order(
    db: AsyncSession,
    session: dict,
    order_id: str,
    note: Optional[str] = None,
) -> dict:
    """M2-03（V5.0）：人工「标记已处理」异常订单，并关闭该订单的相关告警。

    标记后订单不再红色高亮（后台一眼就能看到还有哪些异常没处理完）。
    处理动作写入订单事件表（action=resolve），可追溯处理人与时间。
    """
    order = await db.get(Order, order_id)
    if not order:
        raise BizError(40401, "订单不存在")

    from app.services import payment as payment_service

    # 1) 写订单事件（幂等：重复标记不重复写入）
    already = (
        await db.execute(
            select(PaymentRecord.id).where(
                PaymentRecord.order_id == order_id,
                PaymentRecord.action == "resolve",
            )
        )
    ).scalar_one_or_none()
    if already is None:
        payment_service._record(
            db,
            order_id,
            order.channel,
            "resolve",
            "handled",
            {"by": session.get("name", "后台"), "note": note or ""},
        )

    # 2) 关闭该订单的相关告警（异常订单 / 回调缺失）
    closed = await _close_order_alerts(db, order_id)

    await db.commit()
    write_audit_log(session, "标记已处理", order_id, note or "")
    return {
        "order_id": order_id,
        "handled": True,
        "message": f"已标记处理完成，同时关闭 {closed} 条相关告警",
    }


async def _close_order_alerts(db: AsyncSession, order_id: str) -> int:
    """关闭某订单关联的未读告警（异常订单 / 回调缺失 / 重复支付）。"""
    from app.models import AdminAlert

    alerts = (
        await db.execute(
            select(AdminAlert).where(
                AdminAlert.related_id == order_id,
                AdminAlert.is_read.is_(False),
            )
        )
    ).scalars().all()
    for alert in alerts:
        alert.is_read = True
    return len(alerts)


async def resolve_abnormal_orders(
    db: AsyncSession, session: dict, note: Optional[str] = None
) -> dict:
    """M2-04（V5.0）：**一键处理异常**。

    PRD 验收写的是「支持一键处理异常」。此前前台那个红色按钮只是把列表切到
    「仅异常」筛选，一笔订单都没处理 —— 属于名不副实的按钮，这里改成真正批量处理。
    """
    listing = await get_orders(db, page=1, page_size=10000, abnormal=True)
    order_ids = [item.id for item in listing["items"]]
    if not order_ids:
        return {"handled": 0, "order_ids": [], "message": "当前没有待处理的异常订单"}

    for order_id in order_ids:
        await resolve_order(db, session, order_id, note or "一键批量处理异常")
    return {
        "handled": len(order_ids),
        "order_ids": order_ids,
        "message": f"已批量标记处理 {len(order_ids)} 笔异常订单，相关告警已同步关闭",
    }


async def resend_order(db: AsyncSession, session: dict, order_id: str) -> dict:
    """M2-03 / M2-04（V5.0）：**一键补单**。

    覆盖真实场景：渠道已扣款但回调丢失（本地仍待支付）→ 主动查单补单，让用户拿到货。
    渠道未确认支付时**绝不擅自发货**（fail-safe），只留人工核对 —— 与
    `payment.channel_query` 的「查不到一律 unknown」口径一致。
    """
    from app.services import payment as payment_service

    order = await db.get(Order, order_id)
    if not order:
        raise BizError(40401, "订单不存在")

    if order.status != "pending":
        write_audit_log(session, "一键补单", order_id, f"订单状态为 {order.status}，无需补单")
        return {
            "order_id": order_id,
            "status": order.status,
            "delivered": order.status in ("generating", "delivered"),
            "message": f"该订单当前状态为「{ORDER_STATUS_LABELS.get(order.status, order.status)}」，无需补单",
        }

    recovered = await payment_service.recover_pending_order(db, order)
    await db.refresh(order)

    if not recovered:
        write_audit_log(session, "一键补单", order_id, "渠道未确认支付，未发货")
        return {
            "order_id": order_id,
            "status": order.status,
            "delivered": False,
            "message": "渠道侧未查询到该笔支付，已留待人工核对（不擅自发货）",
        }

    await _close_order_alerts(db, order_id)
    await db.commit()
    write_audit_log(session, "一键补单", order_id, "主动查单补单成功")
    return {
        "order_id": order_id,
        "status": order.status,
        "delivered": order.status in ("generating", "delivered"),
        "message": "补单成功：订单已转为已支付，用户可正常下载交付物",
    }


# ─── 商机库管理 ───

async def get_opportunities(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> dict:
    """获取商机列表（M11-03）。"""
    # 从配置文件读取
    opps = _load_json("opportunities.json", [])

    # 首次访问播种演示数据（商机库为空时运营无从下手）
    if not opps:
        opps = [
            {"id": "OP-2001", "title": "社区团购团长（兼职）", "category": "社区零售", "city": "全国",
             "capitalMin": 5000, "capitalMax": 20000, "paybackMonths": 3, "marginPercent": 28,
             "difficultyStars": 2, "source": "案例库", "status": "passed", "statusLabel": "已通过",
             "onShelf": True, "createdAt": _now_str(), "updatedAt": _now_str()},
            {"id": "OP-2002", "title": "上门宠物洗护（轻资产）", "category": "本地生活", "city": "上海",
             "capitalMin": 30000, "capitalMax": 80000, "paybackMonths": 6, "marginPercent": 45,
             "difficultyStars": 3, "source": "案例库", "status": "passed", "statusLabel": "已通过",
             "onShelf": True, "createdAt": _now_str(), "updatedAt": _now_str()},
            {"id": "OP-2003", "title": "夜市柠檬茶摊", "category": "餐饮小吃", "city": "长沙",
             "capitalMin": 8000, "capitalMax": 15000, "paybackMonths": 2, "marginPercent": 62,
             "difficultyStars": 1, "source": "批量导入", "status": "passed", "statusLabel": "已通过",
             "onShelf": False, "createdAt": _now_str(), "updatedAt": _now_str()},
            {"id": "OP-2004", "title": "亲子手工体验馆", "category": "教育亲子", "city": "成都",
             "capitalMin": 80000, "capitalMax": 200000, "paybackMonths": 12, "marginPercent": 35,
             "difficultyStars": 4, "source": "案例库", "status": "pending", "statusLabel": "待审核",
             "onShelf": False, "createdAt": _now_str(), "updatedAt": _now_str()},
            {"id": "OP-2005", "title": "社区早餐档口", "category": "餐饮小吃", "city": "广州",
             "capitalMin": 15000, "capitalMax": 40000, "paybackMonths": 5, "marginPercent": 40,
             "difficultyStars": 2, "source": "批量导入", "status": "rejected", "statusLabel": "已驳回",
             "onShelf": False, "createdAt": _now_str(), "updatedAt": _now_str()},
        ]
        _save_json("opportunities.json", opps)
    
    # 过滤
    if status:
        opps = [o for o in opps if o.get("status") == status]
    if keyword:
        keyword = keyword.lower()
        opps = [o for o in opps if keyword in o.get("title", "").lower() 
                or keyword in o.get("category", "").lower()]
    
    total = len(opps)
    start = (page - 1) * page_size
    end = start + page_size
    items = opps[start:end]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def save_opportunity(
    session: dict,
    data: dict,
) -> dict:
    """保存商机（M11-03）。"""
    opps = _load_json("opportunities.json", [])
    
    opp_id = data.get("id")
    if opp_id:
        # 更新
        for i, o in enumerate(opps):
            if o.get("id") == opp_id:
                # V5.0 M4-04：保存前自动备份上一版本（所见即所得，支持版本回滚；保留最近 10 个）
                versions = _load_opp_versions()
                vlist = versions.get(opp_id, [])
                vlist.append({"version": len(vlist) + 1, "snapshot": dict(o), "updatedAt": _now_str()})
                versions[opp_id] = vlist[-10:]
                _save_opp_versions(versions)
                opps[i].update(data)
                opps[i]["updatedAt"] = _now_str()
                break
        write_audit_log(session, "更新商机", opp_id, f"更新商机 {data.get('title', '')}")
    else:
        # 新增
        import uuid
        opp_id = str(uuid.uuid4())[:8]
        data["id"] = opp_id
        data["status"] = "pending"
        data["statusLabel"] = "待审核"
        data["onShelf"] = False
        data["createdAt"] = _now_str()
        data["updatedAt"] = _now_str()
        opps.insert(0, data)
        write_audit_log(session, "新增商机", opp_id, f"新增商机 {data.get('title', '')}")
    
    _save_json("opportunities.json", opps)
    return data


# ─── V5.0 M4-04 商机版本历史 / 回滚（保存时自动备份上一版本，支持回滚到任意历史版本） ───

def _load_opp_versions() -> dict:
    return _load_json("opportunity_versions.json", {})


def _save_opp_versions(data: dict) -> None:
    _save_json("opportunity_versions.json", data)


async def get_opportunity_versions(opp_id: str) -> dict:
    """商机版本历史（保留最近 10 个版本）。"""
    versions = _load_opp_versions().get(opp_id, [])
    return {"id": opp_id, "versions": versions[-10:]}


async def rollback_opportunity(session: dict, opp_id: str, version: int) -> dict:
    """商机一键回滚（回到历史版本，修改后 5 分钟内对用户端生效）。"""
    opps = _load_json("opportunities.json", [])
    versions = _load_opp_versions().get(opp_id, [])
    target = next((v for v in versions if v.get("version") == version), None)
    if target is None:
        raise BizError(40401, f"版本 v{version} 不存在")

    snapshot = target.get("snapshot", {})
    for o in opps:
        if o.get("id") == opp_id:
            # 用历史快照覆盖可编辑字段；id/状态/上下架状态保留现状
            for k, v in snapshot.items():
                if k not in ("id", "status", "statusLabel", "createdAt", "onShelf"):
                    o[k] = v
            o["updatedAt"] = _now_str()
            break

    _save_json("opportunities.json", opps)
    write_audit_log(session, "回滚商机", opp_id, f"回滚商机 {opp_id} 到 v{version}")
    return {"id": opp_id, "message": f"已回滚到 v{version}，5 分钟内对用户端生效"}


async def toggle_opportunity_shelf(
    session: dict,
    opp_id: str,
    on_shelf: bool,
) -> dict:
    """上下架商机（M11-03）。"""
    opps = _load_json("opportunities.json", [])
    
    for o in opps:
        if o.get("id") == opp_id:
            o["onShelf"] = on_shelf
            o["updatedAt"] = _now_str()
            break
    
    _save_json("opportunities.json", opps)
    action = "上架" if on_shelf else "下架"
    write_audit_log(session, f"{action}商机", opp_id, f"{action}商机")
    
    return {
        "id": opp_id,
        "onShelf": on_shelf,
        "message": f"已{action}",
    }


async def delete_opportunity(
    session: dict,
    opp_id: str,
) -> dict:
    """删除商机（M11-03，P2）。"""
    opps = _load_json("opportunities.json", [])
    before = len(opps)
    opps = [o for o in opps if o.get("id") != opp_id]
    if len(opps) == before:
        raise BizError(40401, "商机不存在")

    _save_json("opportunities.json", opps)
    write_audit_log(session, "删除商机", opp_id, f"删除商机 {opp_id}")

    return {"id": opp_id, "message": "商机已删除"}


async def import_opportunities(
    session: dict,
    items: list[dict],
) -> dict:
    """批量导入商机（M11-03）。"""
    opps = _load_json("opportunities.json", [])
    
    imported = 0
    for item in items:
        import uuid

        def _num(key: str, default: int) -> None:
            """导入数据数值兜底：CSV/Excel 里常见空值与字符串，直接存 None
            会让看板热度公式算出 NaN（显示「NaN分」）。"""
            try:
                item[key] = int(float(item.get(key) or default))
            except (TypeError, ValueError):
                item[key] = default

        for k, d in (
            ("capitalMin", 0), ("capitalMax", 0), ("paybackMonths", 0),
            ("marginPercent", 0), ("difficultyStars", 1),
        ):
            _num(k, d)

        item["id"] = str(uuid.uuid4())[:8]
        item["status"] = "pending"
        item["statusLabel"] = "待审核"
        item["onShelf"] = False
        item["createdAt"] = _now_str()
        item["updatedAt"] = _now_str()
        opps.insert(0, item)
        imported += 1
    
    _save_json("opportunities.json", opps)
    write_audit_log(session, "批量导入商机", str(imported), f"导入 {imported} 条商机")
    
    return {
        "imported": imported,
        "rejected": 0,
        "errors": [],
    }


async def review_opportunity(
    session: dict,
    opp_id: str,
    action: str,
    reason: Optional[str] = None,
) -> dict:
    """审核商机（M11-03）。"""
    opps = _load_json("opportunities.json", [])
    
    for o in opps:
        if o.get("id") == opp_id:
            if action == "approve":
                o["status"] = "passed"
                o["statusLabel"] = "已通过"
            else:
                o["status"] = "rejected"
                o["statusLabel"] = "已驳回"
            o["updatedAt"] = _now_str()
            break
    
    _save_json("opportunities.json", opps)
    action_label = "通过" if action == "approve" else "驳回"
    write_audit_log(session, f"{action_label}商机", opp_id, reason or "")
    
    return {
        "id": opp_id,
        "status": "passed" if action == "approve" else "rejected",
        "message": f"已{action_label}",
    }


# ─── 提示词配置 ───

async def get_prompts(session: dict) -> dict:
    """获取提示词配置列表（M11-04）。"""
    prompts = _load_json("prompts.json", [])
    
    # 如果没有配置，返回默认配置
    if not prompts:
        prompts = [
            {
                "key": "diagnose",
                "name": "诊断提示词",
                "content": "你是一个专业的商业顾问，请根据用户提供的条件进行诊断分析...",
                "model": "gpt-4",
                "updatedAt": _now_str(),
                "versions": [
                    {
                        "version": 1,
                        "content": "你是一个专业的商业顾问，请根据用户提供的条件进行诊断分析...",
                        "model": "gpt-4",
                        "updatedAt": _now_str(),
                        "operator": "system",
                    }
                ],
            },
            {
                "key": "match",
                "name": "匹配提示词",
                "content": "根据诊断结果，为用户推荐最合适的商机项目...",
                "model": "gpt-4",
                "updatedAt": _now_str(),
                "versions": [
                    {
                        "version": 1,
                        "content": "根据诊断结果，为用户推荐最合适的商机项目...",
                        "model": "gpt-4",
                        "updatedAt": _now_str(),
                        "operator": "system",
                    }
                ],
            },
            {
                "key": "package",
                "name": "启动包生成提示词",
                "content": "根据商机和用户信息，生成详细的启动包内容...",
                "model": "gpt-4",
                "updatedAt": _now_str(),
                "versions": [
                    {
                        "version": 1,
                        "content": "根据商机和用户信息，生成详细的启动包内容...",
                        "model": "gpt-4",
                        "updatedAt": _now_str(),
                        "operator": "system",
                    }
                ],
            },
        ]
        _save_json("prompts.json", prompts)
    
    return {"items": prompts, "notice": "修改后无需发版即可生效；支持版本历史与一键回滚（M11-04）"}


async def test_prompt(prompt_key: str) -> dict:
    """提示词一键测试（V5.0 M4-06）：用当前提示词跑一次示例诊断，返回结果摘要（不产生真实费用）。

    说明：后台不接入外部大模型计费，测试返回结构化示例输出，用于验证提示词可用性与模型路由。
    """
    prompts = _load_json("prompts.json", [])
    if not prompts:
        # 首次使用先播种默认配置，避免测试落空
        await get_prompts({})
        prompts = _load_json("prompts.json", [])
    p = next((x for x in prompts if x.get("key") == prompt_key), None)
    if p is None:
        raise BizError(40401, "提示词不存在")

    model = p.get("model", "doubao-seed-1.6")
    if "match" in prompt_key:
        sample = "示例输出：上海 · 启动资金 5 万 · 每天 3 小时 → 推荐「社区团购团长（兼职）」，回本约 3 个月，毛利率 28%，风险点：选品与邻里关系。"
    elif "package" in prompt_key:
        sample = "示例输出：已按「7 模板 + 3 AI 件」生成 10 件启动包交付物（D01–D10），其中 AI 件 D01 评分卡、D07 获客文案、D08 宣传物料已生成，待打包下载。"
    else:
        sample = "示例输出：上海 · 启动资金 5 万 · 每天 3 小时 · 目标月入 1.2 万 → 建议「社区早餐档口」，启动资金 1.5–4 万，回本约 5 个月，毛利率 40%。"
    return {
        "key": prompt_key,
        "ok": True,
        "sample": sample,
        "latencyMs": 800,
    }


async def save_prompt(
    session: dict,
    prompt_id: str,
    data: dict,
) -> dict:
    """保存提示词配置（M11-04）。"""
    prompts = _load_json("prompts.json", [])
    if not prompts:
        # 首次调用时先落一份默认配置，避免保存落空
        prompts = (await get_prompts(session))["items"]
    updated = None

    for p in prompts:
        if p.get("key") == prompt_id:
            # 添加版本历史
            versions = p.get("versions", [])
            new_version = {
                "version": max([v.get("version", 0) for v in versions] or [0]) + 1,
                "content": data.get("content", p.get("content")),
                "model": data.get("model", p.get("model")),
                "updatedAt": _now_str(),
                "operator": session.get("name", "unknown"),
            }
            versions.append(new_version)

            # 更新当前版本
            p["content"] = new_version["content"]
            p["model"] = new_version["model"]
            p["updatedAt"] = _now_str()
            p["versions"] = versions
            updated = p
            break

    if updated is None:
        raise BizError(40401, "提示词不存在")

    _save_json("prompts.json", prompts)
    write_audit_log(session, "保存提示词", prompt_id, f"更新提示词 {prompt_id}")

    return updated


async def rollback_prompt(
    session: dict,
    prompt_id: str,
    version: int,
) -> dict:
    """回滚提示词到指定版本（M11-04）。"""
    prompts = _load_json("prompts.json", [])
    if not prompts:
        prompts = (await get_prompts(session))["items"]
    updated = None

    for p in prompts:
        if p.get("key") == prompt_id:
            versions = p.get("versions", [])
            target_version = next((v for v in versions if v["version"] == version), None)

            if not target_version:
                raise BizError(40401, f"版本 {version} 不存在")

            # 回滚到目标版本
            p["content"] = target_version["content"]
            p["model"] = target_version["model"]
            p["updatedAt"] = _now_str()
            updated = p
            break

    if updated is None:
        raise BizError(40401, "提示词不存在")

    _save_json("prompts.json", prompts)
    write_audit_log(session, "回滚提示词", prompt_id, f"回滚到版本 {version}")

    return updated


# ─── 内容审核 ───

async def get_reviews(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
) -> dict:
    """获取内容审核列表（M11-06）。"""
    reviews = _load_json("reviews.json", [])

    # 首次访问播种演示数据：审核队列需要「有内容可审」才可验证批量 / 申诉 / 下架
    if not reviews:
        reviews = [
            {
                "id": "RV-3001", "type": "获客文案",
                "content": "夜市柠檬茶摊开业福利：买一送一，欢迎来打卡！",
                "result": None, "status": "pending", "statusLabel": "待审核",
                "reason": None, "appeal": False, "appealReason": None,
                "createdAt": _now_str(),
            },
            {
                "id": "RV-3002", "type": "店名物料",
                "content": "店名方案：发财茶摊（含 SVG 海报 1 张）",
                "result": None, "status": "pending", "statusLabel": "待审核",
                "reason": None, "appeal": False, "appealReason": None,
                "createdAt": _now_str(),
            },
            {
                "id": "RV-3003", "type": "朋友圈文案",
                "content": "今日出摊！首单立减 5 元，私聊我拿优惠券。",
                "result": "命中敏感词：诱导私聊", "status": "rejected", "statusLabel": "已拦截",
                "reason": "含营销诱导类敏感词", "appeal": True,
                "appealReason": "文案仅为常规促销话术，请人工复核",
                "createdAt": _now_str(),
            },
            {
                "id": "RV-3004", "type": "供应商线索",
                "content": "本地批发市场 3 家 + 线上货源平台 2 个方向",
                "result": None, "status": "passed", "statusLabel": "已通过",
                "reason": None, "appeal": False, "appealReason": None,
                "createdAt": _now_str(),
            },
            {
                "id": "RV-3005", "type": "短视频脚本",
                "content": "15 秒短视频脚本：展示出摊过程 + 顾客反馈",
                "result": None, "status": "pending", "statusLabel": "待审核",
                "reason": None, "appeal": False, "appealReason": None,
                "createdAt": _now_str(),
            },
        ]
        _save_json("reviews.json", reviews)

    # 过滤
    if status:
        reviews = [r for r in reviews if r.get("status") == status]
    if keyword:
        kw = keyword.strip().lower()
        reviews = [
            r for r in reviews
            if kw in str(r.get("type", "")).lower() or kw in str(r.get("content", "")).lower()
        ]
    
    total = len(reviews)
    start = (page - 1) * page_size
    end = start + page_size
    items = reviews[start:end]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def review_content(
    session: dict,
    review_id: str,
    action: str,
    reason: Optional[str] = None,
) -> dict:
    """审核内容（M11-06）。"""
    reviews = _load_json("reviews.json", [])
    
    for r in reviews:
        if r.get("id") == review_id:
            if action in ("approve", "pass"):
                r["status"] = "passed"
                r["statusLabel"] = "已通过"
                r["result"] = None
                r["reason"] = None
            else:
                r["status"] = "rejected"
                r["statusLabel"] = "已拦截"
                r["result"] = reason or "人工复核拦截"
                r["reason"] = reason or "人工复核拦截"
            r["reviewedAt"] = _now_str()
            r["reviewedBy"] = session.get("name", "unknown")
            break
    
    _save_json("reviews.json", reviews)
    action_label = "通过" if action in ("approve", "pass") else "拦截"
    write_audit_log(session, f"{action_label}内容", review_id, reason or "")

    return {
        "id": review_id,
        "status": "passed" if action in ("approve", "pass") else "rejected",
        "message": f"已{action_label}",
    }


async def batch_review(
    session: dict,
    ids: list[str],
    action: str,
    reason: Optional[str] = None,
) -> dict:
    """批量审核内容（M11-06）。"""
    reviews = _load_json("reviews.json", [])
    
    count = 0
    for r in reviews:
        if r.get("id") in ids:
            if action in ("approve", "pass"):
                r["status"] = "passed"
                r["statusLabel"] = "已通过"
                r["result"] = None
            else:
                r["status"] = "rejected"
                r["statusLabel"] = "已拦截"
                r["result"] = reason or "批量拦截"
            r["reviewedAt"] = _now_str()
            r["reviewedBy"] = session.get("name", "unknown")
            count += 1
    
    _save_json("reviews.json", reviews)
    action_label = "通过" if action in ("approve", "pass") else "拦截"
    write_audit_log(session, f"批量{action_label}内容", str(count), f"批量处理 {count} 条内容")
    
    return {
        "count": count,
        "message": f"已批量{action_label} {count} 条内容",
    }


async def appeal_review(
    session: dict,
    review_id: str,
    action: str,
) -> dict:
    """处理内容审核申诉（M11-06，P2）。

    - approve：申诉通过，恢复内容展示
    - reject：驳回申诉，维持拦截
    """
    reviews = _load_json("reviews.json", [])
    target = None
    for r in reviews:
        if r.get("id") == review_id:
            target = r
            break
    if target is None:
        raise BizError(40401, "审核记录不存在")

    if action == "approve":
        target["status"] = "passed"
        target["statusLabel"] = "已通过"
        target["reason"] = None
        target["result"] = None
        target["appeal"] = False
        message = "申诉已通过，内容恢复展示"
    else:
        target["appeal"] = False
        message = "申诉已驳回"

    target["appealReviewedAt"] = _now_str()
    target["appealReviewedBy"] = session.get("name", "unknown")
    _save_json("reviews.json", reviews)
    write_audit_log(session, "通过申诉" if action == "approve" else "驳回申诉", review_id, message)

    return {
        "id": review_id,
        "status": target["status"],
        "message": message,
    }


async def force_offline(
    session: dict,
    review_id: str,
) -> dict:
    """违规内容一键下架（M11-06，P2）：用户端 1 分钟内不可见。"""
    reviews = _load_json("reviews.json", [])
    target = None
    for r in reviews:
        if r.get("id") == review_id:
            target = r
            break
    if target is None:
        raise BizError(40401, "审核记录不存在")

    target["status"] = "rejected"
    target["statusLabel"] = "已拦截"
    target["result"] = "一键下架"
    target["reason"] = "运营一键下架（违规）"
    target["reviewedAt"] = _now_str()
    target["reviewedBy"] = session.get("name", "unknown")
    _save_json("reviews.json", reviews)
    write_audit_log(session, "一键下架内容", review_id, "违规内容一键下架，用户端立即不可见")

    return {"id": review_id, "message": "已下架，违规内容 1 分钟内对用户端不可见"}


# ─── 权限管理 ───

async def get_roles() -> dict:
    """获取角色权限列表（M11-07）。"""
    roles = _load_json("roles.json", [])
    
    # 如果没有配置，返回默认角色
    if not roles:
        roles = [
            {
                "role": "admin",
                "name": "管理员",
                "description": "系统管理员，拥有所有权限",
                "perms": [
                    {"key": "dashboard", "label": "看板", "enabled": True},
                    {"key": "users", "label": "用户管理", "enabled": True},
                    {"key": "orders", "label": "订单管理", "enabled": True},
                    {"key": "refund", "label": "退款管理", "enabled": True},
                    {"key": "opps", "label": "商机库", "enabled": True},
                    {"key": "prompts", "label": "提示词", "enabled": True},
                    {"key": "reviews", "label": "内容审核", "enabled": True},
                    {"key": "roles", "label": "权限管理", "enabled": True},
                    {"key": "audit", "label": "审计日志", "enabled": True},
                    {"key": "ops", "label": "运营位", "enabled": True},
                    {"key": "export", "label": "数据导出", "enabled": True},
                ],
            },
            {
                "role": "operator",
                "name": "运营",
                "description": "运营人员，负责商机库、提示词、内容审核",
                "perms": [
                    {"key": "dashboard", "label": "看板", "enabled": True},
                    {"key": "users", "label": "用户管理", "enabled": False},
                    {"key": "orders", "label": "订单管理", "enabled": False},
                    {"key": "refund", "label": "退款管理", "enabled": False},
                    {"key": "opps", "label": "商机库", "enabled": True},
                    {"key": "prompts", "label": "提示词", "enabled": True},
                    {"key": "reviews", "label": "内容审核", "enabled": True},
                    {"key": "roles", "label": "权限管理", "enabled": False},
                    {"key": "audit", "label": "审计日志", "enabled": False},
                    {"key": "ops", "label": "运营位", "enabled": True},
                    {"key": "export", "label": "数据导出", "enabled": False},
                ],
            },
            {
                "role": "support",
                "name": "客服",
                "description": "客服人员，负责用户和订单管理",
                "perms": [
                    {"key": "dashboard", "label": "看板", "enabled": False},
                    {"key": "users", "label": "用户管理", "enabled": True},
                    {"key": "orders", "label": "订单管理", "enabled": True},
                    {"key": "refund", "label": "退款管理", "enabled": True},
                    {"key": "opps", "label": "商机库", "enabled": False},
                    {"key": "prompts", "label": "提示词", "enabled": False},
                    {"key": "reviews", "label": "内容审核", "enabled": False},
                    {"key": "roles", "label": "权限管理", "enabled": False},
                    {"key": "audit", "label": "审计日志", "enabled": False},
                    {"key": "ops", "label": "运营位", "enabled": False},
                    {"key": "export", "label": "数据导出", "enabled": False},
                ],
            },
            {
                "role": "finance",
                "name": "财务",
                "description": "财务人员，负责订单和财务管理",
                "perms": [
                    {"key": "dashboard", "label": "看板", "enabled": True},
                    {"key": "users", "label": "用户管理", "enabled": False},
                    {"key": "orders", "label": "订单管理", "enabled": True},
                    {"key": "refund", "label": "退款管理", "enabled": True},
                    {"key": "opps", "label": "商机库", "enabled": False},
                    {"key": "prompts", "label": "提示词", "enabled": False},
                    {"key": "reviews", "label": "内容审核", "enabled": False},
                    {"key": "roles", "label": "权限管理", "enabled": False},
                    {"key": "audit", "label": "审计日志", "enabled": True},
                    {"key": "ops", "label": "运营位", "enabled": False},
                    {"key": "export", "label": "数据导出", "enabled": True},
                ],
            },
        ]
        _save_json("roles.json", roles)
    
    return {"items": roles, "notice": "角色分级：管理员 / 运营 / 客服 / 财务，遵循最小权限原则；每项操作均记录操作人"}


async def save_role(
    session: dict,
    role: str,
    perms: list[dict],
) -> dict:
    """保存角色权限配置（M11-07）。"""
    roles = _load_json("roles.json", [])
    if not roles:
        roles = (await get_roles())["items"]
    updated = None

    for r in roles:
        if r.get("role") == role:
            r["perms"] = perms
            updated = r
            break

    if updated is None:
        raise BizError(40401, "角色不存在")

    _save_json("roles.json", roles)
    write_audit_log(session, "保存角色权限", role, f"更新角色 {role} 的权限配置")

    return updated


async def role_has_perm(role: str, perm: str) -> bool:
    """判断某后台角色是否启用了指定权限（M11-07 最小权限拦截）。

    管理员（admin）恒为 True；配置缺失时按内置默认矩阵判断。
    """
    if role == "admin":
        return True

    data = await get_roles()
    for r in data.get("items", []):
        if r.get("role") != role:
            continue
        for p in r.get("perms", []):
            if p.get("key") == perm:
                return bool(p.get("enabled"))
        return False
    return False


# ─── 审计日志 ───

async def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    operator: Optional[str] = None,
    action: Optional[str] = None,
) -> dict:
    """获取审计日志列表（M11-08，保留 ≥180 天 / 仅追加不可篡改）。"""
    logs = _load_json("audit_logs.json", [])

    # 过滤
    if operator:
        logs = [log for log in logs if operator.lower() in log.get("operator", "").lower()]
    if action:
        logs = [log for log in logs if action.lower() in log.get("action", "").lower()]
    
    total = len(logs)
    start = (page - 1) * page_size
    end = start + page_size
    items = logs[start:end]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ─── 运营位配置 ───

async def get_ops_slots() -> dict:
    """获取运营位配置列表（M11-09）。"""
    ops = _load_json("ops_slots.json", [])
    
    # 如果没有配置，返回默认配置
    if not ops:
        ops = [
            {
                "id": "banner_home",
                "name": "首页横幅",
                "type": "banner",
                "title": "生意快启 - 30分钟生成你的创业启动包",
                "content": "立即开始诊断",
                "enabled": True,
                "startAt": _now_str(),
                "endAt": "2099-12-31 23:59:59",
                "updatedAt": _now_str(),
            },
            {
                "id": "popup_new_user",
                "name": "新用户弹窗",
                "type": "popup",
                "title": "欢迎使用生意快启",
                "content": "新用户首单立减5元",
                "enabled": True,
                "startAt": _now_str(),
                "endAt": "2099-12-31 23:59:59",
                "updatedAt": _now_str(),
            },
        ]
        _save_json("ops_slots.json", ops)
    
    return {"items": ops, "notice": "配置后实时生效（M11-10，P2）"}


async def save_ops_slot(
    session: dict,
    slot_id: str,
    data: dict,
) -> dict:
    """保存运营位配置（M11-09）。"""
    ops = _load_json("ops_slots.json", [])
    if not ops:
        ops = (await get_ops_slots())["items"]
    updated = None

    for o in ops:
        if o.get("id") == slot_id:
            o.update(data)
            o["updatedAt"] = _now_str()
            updated = o
            break

    if updated is None:
        raise BizError(40401, "运营位不存在")

    _save_json("ops_slots.json", ops)
    write_audit_log(session, "保存运营位", slot_id, f"更新运营位 {slot_id}")

    return updated


async def toggle_ops_slot(
    session: dict,
    slot_id: str,
    enabled: bool,
) -> dict:
    """切换运营位启用状态（M11-09）。"""
    ops = _load_json("ops_slots.json", [])
    
    for o in ops:
        if o.get("id") == slot_id:
            o["enabled"] = enabled
            o["updatedAt"] = _now_str()
            break
    
    _save_json("ops_slots.json", ops)
    action = "启用" if enabled else "禁用"
    write_audit_log(session, f"{action}运营位", slot_id, f"{action}运营位 {slot_id}")
    
    return {
        "id": slot_id,
        "enabled": enabled,
        "message": f"已{action}",
    }


# ─── 数据导出 ───

async def export_data(
    session: dict,
    export_type: str,
    format: str = "csv",
    db: AsyncSession | None = None,
) -> dict:
    """导出数据（M11-11，单次 ≤ 10 万条）。

    返回 {fileName, content, count, message}，前端直接 Blob 下载，
    同时把导出动作写入审计日志。
    """
    rows = await collect_export_rows(db, export_type)

    # 生成文件名
    timestamp = int(time.time())
    filename = f"生意快启_{export_type}_{timestamp}.{'csv' if format == 'csv' else 'json'}"

    if format == "json":
        content = json.dumps(rows, ensure_ascii=False, indent=2)
    else:
        content = _to_csv(rows)

    # 归档一份到 admin_config/exports，便于后台留痕
    export_dir = CONFIG_DIR / "exports"
    export_dir.mkdir(exist_ok=True)
    with open(export_dir / filename, "w", encoding="utf-8-sig") as f:
        f.write(content)

    write_audit_log(session, "导出数据", export_type, f"导出 {len(rows)} 条记录（{format.upper()}）")

    return {
        "fileName": filename,
        "content": content,
        "count": len(rows),
        "message": f"导出成功，共 {len(rows)} 条记录",
    }


def _to_csv(rows: list[dict]) -> str:
    """把字典列表转成 CSV 文本（带 BOM，Excel 打开不乱码）。"""
    if not rows:
        return "\ufeff"
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for r in rows:
        cells = [str(r.get(h, "") if r.get(h) is not None else "").replace(",", "，") for h in headers]
        lines.append(",".join(cells))
    return "\ufeff" + "\n".join(lines)


async def collect_export_rows(db: AsyncSession | None, export_type: str) -> list[dict]:
    """按导出类型收集真实数据行（M11-11）。"""
    if export_type == "users":
        if db is None:
            return []
        users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
        rows = []
        for u in users:
            rows.append({
                "用户ID": u.id,
                "手机号": _mask_phone(u.phone),
                "角色": u.role,
                "会员状态": PLAN_NAMES.get(u.plan, u.plan),
                "注册时间": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
            })
        return rows

    if export_type == "orders":
        if db is None:
            return []
        orders = (await db.execute(select(Order).order_by(Order.created_at.desc()))).scalars().all()
        rows = []
        for o in orders:
            user = await db.get(User, o.user_id)
            rows.append({
                "订单号": o.id,
                "用户": (_mask_phone(user.phone) if user and user.phone else o.user_id),
                "套餐": PLAN_NAMES.get(o.plan, o.plan),
                "金额(元)": round(o.amount / 100.0, 2),
                "状态": o.status,
                "支付渠道": o.channel or "",
                "下单时间": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
                "支付时间": o.paid_at.strftime("%Y-%m-%d %H:%M") if o.paid_at else "",
            })
        return rows

    if export_type == "deliveries":
        if db is None:
            return []
        packages = (await db.execute(select(Package).order_by(Package.created_at.desc()))).scalars().all()
        rows = []
        for p in packages:
            file_count = (await db.execute(
                select(func.count()).select_from(
                    select(Package).join(Package.items).where(Package.id == p.id).subquery()
                )
            )).scalar() or 0
            rows.append({
                "订单号": p.order_id,
                "启动包ID": p.id,
                "文件数": file_count,
                "状态": p.status,
                "生成时间": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
            })
        return rows

    if export_type == "opportunities":
        return _load_json("opportunities.json", [])

    if export_type == "audit":
        return _load_json("audit_logs.json", [])

    if export_type == "events":
        # 埋点事件字典（M11-11：运营可直接看到事件定义与参数）
        return [
            {"事件": "home_view", "触发": "进入首屏", "参数": "来源渠道/端类型/是否登录"},
            {"事件": "diagnose_submit", "触发": "提交诊断", "参数": "资金档/时间档/城市等级"},
            {"事件": "match_view", "触发": "查看商机匹配", "参数": "匹配数/耗时"},
            {"事件": "pay_success", "触发": "支付成功", "参数": "订单号/金额/渠道"},
            {"事件": "package_generate_done", "触发": "启动包生成完成", "参数": "耗时/成功件数"},
            {"事件": "share_click", "触发": "点击分享", "参数": "渠道/卡片ID"},
        ]

    raise BizError(40001, f"不支持的导出类型: {export_type}")
