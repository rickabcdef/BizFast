"""分享与增长路由 - 负责人 D - 对应 m8_share / m8-03 / m8-04 / m11_admin 分享概览

路径见 docs/api-contract.md（M8 / M11-D）。
业务逻辑见 app/services/share.py。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.context import current_owner, ensure_owner_user
from app.core.database import get_db
from app.core.errors import BizError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models import User
from app.schemas.common import ok
from app.schemas.share import BindInviteIn, ShareCardIn, ShareTrackIn
from app.services import share as share_service

router = APIRouter(prefix="/api", tags=["share"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """M11 后台鉴权：Bearer 中解码 user_id，校验 admin/operator/support 角色。

    失败一律返回中文 BizError（不抛英文 401），符合 ADR-006「错误全中文化」。
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise BizError(40101, "请先登录管理员账号")
    try:
        uid = decode_token(auth.split(" ", 1)[1], ACCESS_TOKEN_TYPE)
    except Exception:
        raise BizError(40101, "登录已过期，请重新登录")
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None or user.role not in ("admin", "operator", "support"):
        raise BizError(40101, "无权限访问该后台")
    return user


@router.post("/share/card", summary="生成成果分享卡片（M8-01）")
async def create_share_card(
    payload: ShareCardIn, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    return ok(
        await share_service.create_card(
            db, owner, payload.productName, payload.subtitle,
            payload.lines, payload.qrText, payload.inviterCode,
        ),
        _rid(request),
    )


@router.get("/share/{card_id}", summary="获取分享卡片数据（M8-01）")
async def get_share_card(card_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    return ok(await share_service.get_card(db, card_id), _rid(request))


@router.post("/share/track", summary="分享行为埋点（M8-02）")
async def track_share(payload: ShareTrackIn, request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await share_service.track_event(db, owner, payload.cardId, payload.channel), _rid(request))


@router.get("/share/invite/info", summary="我的邀请信息（M8-03，实时可见）")
async def invite_info(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await share_service.invite_info(db, owner), _rid(request))


@router.post("/share/invite/bind", summary="绑定邀请人（M8-03，幂等）")
async def bind_invite(payload: BindInviteIn, request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    user = await ensure_owner_user(db, owner)
    return ok(await share_service.bind_invite(db, payload.inviterCode, user), _rid(request))


@router.get("/admin/share/stats", summary="分享转化概览（M8-04 / M11-D）")
async def admin_share_stats(
    request: Request, db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)
):
    return ok(await share_service.get_share_stats(db), _rid(request))
