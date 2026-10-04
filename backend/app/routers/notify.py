"""消息与提醒 - 负责人 A - 对应 m9_notify

路由前缀: /api/notify
契约: docs/api-contract.md「M9 消息」
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_owner
from app.core.database import get_db
from app.schemas.common import ok
from app.schemas.notify import NotifySettingIn
from app.services import notify as notify_service

router = APIRouter(prefix="/api/notify", tags=["notify"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("/subscribe", summary="当前端的通知能力与开关（如实标注 Web 端不支持后台通知）")
async def subscribe(request: Request, platform: str = Query("web")):
    return ok(notify_service.subscribe_info(platform), _rid(request))


@router.get("/messages", summary="站内消息中心（M9-01）")
async def messages(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50, alias="pageSize"),
    category: str | None = Query(None),
    unread_only: bool = Query(False, alias="unreadOnly"),
    db: AsyncSession = Depends(get_db),
):
    owner = current_owner(request)
    data = await notify_service.list_notifications(
        db, owner.owner_key, page, page_size, category, unread_only
    )
    return ok(data, _rid(request))


@router.get("/unread", summary="未读消息数（红点）")
async def unread(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok({"unread": await notify_service.unread_count(db, owner.owner_key)}, _rid(request))


@router.post("/read", summary="标记已读（传 id 标记单条，不传则全部已读）")
async def mark_read(
    request: Request,
    notification_id: str | None = Query(None, alias="id"),
    db: AsyncSession = Depends(get_db),
):
    owner = current_owner(request)
    count = await notify_service.mark_read(db, owner.owner_key, notification_id)
    return ok(
        {"updated": count, "unread": await notify_service.unread_count(db, owner.owner_key)},
        _rid(request),
    )


@router.get("/settings", summary="消息订阅与免打扰设置")
async def get_settings(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    setting = await notify_service.ensure_setting(db, owner.owner_key)
    return ok(notify_service.setting_payload(setting), _rid(request))


@router.put("/settings", summary="更新消息订阅与免打扰设置（M9-06）")
async def update_settings(
    payload: NotifySettingIn, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    data = await notify_service.update_setting(db, owner.owner_key, payload)
    return ok(data, _rid(request))
