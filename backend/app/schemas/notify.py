"""M9 消息与提醒 schema（负责人 A）。"""
from __future__ import annotations

from app.schemas.common import CamelModel


class NotificationOut(CamelModel):
    id: str
    category: str
    category_label: str
    title: str
    content: str
    link: str | None
    is_read: bool
    created_at: str


class NotifyListOut(CamelModel):
    items: list[NotificationOut]
    unread: int
    total: int
    page: int
    page_size: int


class NotifySettingOut(CamelModel):
    service_notice: bool
    app_push: bool
    desktop_notice: bool
    market_reminder: bool
    dnd_enabled: bool
    dnd_start: str
    dnd_end: str


class NotifySettingIn(CamelModel):
    service_notice: bool | None = None
    app_push: bool | None = None
    desktop_notice: bool | None = None
    market_reminder: bool | None = None
    dnd_enabled: bool | None = None
    dnd_start: str | None = None
    dnd_end: str | None = None


class SubscribeItem(CamelModel):
    key: str
    label: str
    description: str
    supported: bool
    enabled: bool
    platform_note: str


class SubscribeOut(CamelModel):
    platform: str
    items: list[SubscribeItem]
    notice: str
