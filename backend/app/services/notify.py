"""M9 消息与提醒 业务逻辑层 - 负责人 A

PRD 第 4.9 节仅给出标题，本模块按以下口径落地：
- M9-01 站内消息中心：统一收拢系统 / 订单 / 交付 / 退款 / 活动通知，未读红点
- M9-02 微信服务通知（端能力，Web 端不支持，如实标注 supported=false）
- M9-03 App 系统推送（端能力，同上）
- M9-04 桌面端通知（P2，配置项先就位）
- M9-05 商机库更新提醒（会员可关闭）
- M9-06 免打扰时段：时段内不推送营销类消息（订单/退款等交易类不受影响）

Web 端受浏览器限制不支持后台通知，生成完成通过页面内提示 + 短信/邮件提醒（PRD 8.2），
因此 subscribe_info 会按端返回 supported 标记，前端据此禁用开关，不误导用户。
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.context import owner_key_for_user
from app.core.errors import BizError
from app.models import Notification, NotifySetting, User

CATEGORY_LABELS = {
    "system": "系统通知",
    "order": "订单通知",
    "package": "交付通知",
    "refund": "退款通知",
    "activity": "活动通知",
}

# 交易类消息不受免打扰限制（用户必须收到钱相关的消息）
TRANSACTIONAL_CATEGORIES = {"order", "package", "refund"}

MAX_PAGE_SIZE = 50


# ---------------------------------------------------------------- 通知写入
async def create_notification(
    db,
    owner_key: str,
    category: str,
    title: str,
    content: str = "",
    link: str | None = None,
) -> Notification:
    item = Notification(
        id=str(uuid.uuid4()),
        owner_key=owner_key,
        category=category if category in CATEGORY_LABELS else "system",
        title=title,
        content=content,
        link=link,
    )
    db.add(item)
    await db.flush()
    return item


async def create_notification_for_user(
    db,
    user_id: str | None,
    category: str,
    title: str,
    content: str = "",
    link: str | None = None,
) -> None:
    """供订单/交付链路调用（按 user_id 定位归属键）。"""
    if not user_id:
        return
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return
    await create_notification(db, owner_key_for_user(user), category, title, content, link)


# ---------------------------------------------------------------- 设置
async def ensure_setting(db, owner_key: str) -> NotifySetting:
    setting = (
        await db.execute(select(NotifySetting).where(NotifySetting.owner_key == owner_key))
    ).scalar_one_or_none()
    if setting is None:
        setting = NotifySetting(
            id=str(uuid.uuid4()),
            owner_key=owner_key,
            dnd_start=settings.notify_dnd_default_start,
            dnd_end=settings.notify_dnd_default_end,
        )
        db.add(setting)
        await db.commit()
        await db.refresh(setting)
    return setting


def setting_payload(setting: NotifySetting) -> dict:
    return {
        "service_notice": setting.service_notice,
        "app_push": setting.app_push,
        "desktop_notice": setting.desktop_notice,
        "market_reminder": setting.market_reminder,
        "dnd_enabled": setting.dnd_enabled,
        "dnd_start": setting.dnd_start,
        "dnd_end": setting.dnd_end,
    }


async def update_setting(db, owner_key: str, payload) -> dict:
    setting = await ensure_setting(db, owner_key)
    data = payload.model_dump(exclude_none=True, by_alias=False)
    for field in (
        "service_notice",
        "app_push",
        "desktop_notice",
        "market_reminder",
        "dnd_enabled",
    ):
        if field in data:
            setattr(setting, field, bool(data[field]))
    for field in ("dnd_start", "dnd_end"):
        if field in data and data[field]:
            value = str(data[field])
            if not _valid_hhmm(value):
                raise BizError(40001, "免打扰时间格式应为 HH:MM，例如 22:00")
            setattr(setting, field, value)
    await db.commit()
    await db.refresh(setting)
    return setting_payload(setting)


def _valid_hhmm(value: str) -> bool:
    try:
        hh, mm = value.split(":")
        return 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
    except Exception:
        return False


# ---------------------------------------------------------------- 免打扰判定（M9-06）
def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def in_dnd(setting: NotifySetting, now: datetime | None = None) -> bool:
    if not setting.dnd_enabled:
        return False
    now = now or datetime.now()
    start = _parse_hhmm(setting.dnd_start)
    end = _parse_hhmm(setting.dnd_end)
    current = now.time()
    if start <= end:
        return start <= current <= end
    # 跨零点，例如 22:00–08:00
    return current >= start or current <= end


def should_push(setting: NotifySetting, category: str, now: datetime | None = None) -> bool:
    """免打扰时段内不推送营销类消息；交易类消息照常推送（M9-06）。"""
    if category in TRANSACTIONAL_CATEGORIES:
        return True
    return not in_dnd(setting, now)


# ---------------------------------------------------------------- 消息中心（M9-01）
async def list_notifications(
    db,
    owner_key: str,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    unread_only: bool = False,
) -> dict:
    page = max(1, int(page or 1))
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size or 20)))

    conditions = [Notification.owner_key == owner_key]
    if category and category in CATEGORY_LABELS:
        conditions.append(Notification.category == category)
    if unread_only:
        conditions.append(Notification.is_read.is_(False))

    total = (
        await db.execute(select(func.count()).select_from(Notification).where(*conditions))
    ).scalar_one()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.owner_key == owner_key, Notification.is_read.is_(False))
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [_item_payload(row) for row in rows],
        "unread": int(unread),
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _item_payload(row: Notification) -> dict:
    created = row.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": row.id,
        "category": row.category,
        "category_label": CATEGORY_LABELS.get(row.category, "系统通知"),
        "title": row.title,
        "content": row.content or "",
        "link": row.link,
        "is_read": bool(row.is_read),
        "created_at": created.isoformat().replace("+00:00", "Z") if created else "",
    }


async def unread_count(db, owner_key: str) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.owner_key == owner_key, Notification.is_read.is_(False))
            )
        ).scalar_one()
    )


async def mark_read(db, owner_key: str, notification_id: str | None = None) -> int:
    conditions = [Notification.owner_key == owner_key, Notification.is_read.is_(False)]
    if notification_id:
        conditions.append(Notification.id == notification_id)
    rows = (await db.execute(select(Notification).where(*conditions))).scalars().all()
    for row in rows:
        row.is_read = True
    await db.commit()
    return len(rows)


# ---------------------------------------------------------------- 订阅能力（M9-02/03/04）
def subscribe_info(platform: str) -> dict:
    """按端如实说明通知能力，不误导用户开启用不了的能力（PRD 8.2）。"""
    is_weapp = platform == "weapp"
    is_app = platform in ("android", "ios")
    is_desktop = platform in ("win", "mac")
    is_web = platform in ("web", "h5") or platform not in ("weapp", "android", "ios", "win", "mac")

    items = [
        {
            "key": "service_notice",
            "label": "微信服务通知",
            "description": "生成完成、退款到账、会员到期时通过微信服务通知提醒",
            "supported": is_weapp,
            "enabled": is_weapp,
            "platform_note": "仅微信小程序端可用" if not is_weapp else "已接入微信订阅消息",
        },
        {
            "key": "app_push",
            "label": "App 系统推送",
            "description": "通过手机系统推送，离开页面也能收到提醒",
            "supported": is_app,
            "enabled": is_app,
            "platform_note": "仅 App 端可用" if not is_app else "已接入厂商推送通道",
        },
        {
            "key": "desktop_notice",
            "label": "桌面端通知",
            "description": "Windows / macOS 原生通知，点击可跳转对应页面",
            "supported": is_desktop,
            "enabled": is_desktop,
            "platform_note": "仅桌面端可用" if not is_desktop else "已接入系统通知",
        },
    ]

    if is_web:
        notice = "网页版受浏览器限制，暂不支持后台通知；生成完成后会在页面内提示，并可通过短信 / 邮件提醒你。"
    else:
        notice = "可在下方按类型开关通知；交易类消息（支付、退款、交付）始终提醒，不受免打扰限制。"

    return {"platform": platform, "items": items, "notice": notice}
