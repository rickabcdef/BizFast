"""账号体系 - 负责人 D - 对应 m10_user / m1_home

职责：手机号/微信登录、游客态个人中心、订单列表、注销（15 日清数据）、邀请绑定入口。
业务逻辑全部在此，路由层只做参数校验与统一响应（见 app/schemas/common.ok）。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.context import ensure_owner_user
from app.core.errors import BizError
from app.core.security import create_access_token
from app.models import Order, User
from app.services import share as share_service

_PURGE_DAYS = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) != 11:
        return phone
    return f"{phone[:3]}****{phone[6:]}"


async def _gen_invite_code(db) -> str:
    """生成唯一邀请码（BF- + 5 位 base36）。"""
    from sqlalchemy import func

    while True:
        code = "BF-" + uuid.uuid4().hex[:5].upper()
        exists = (
            await db.execute(
                select(func.count()).select_from(User).where(User.invite_code == code)
            )
        ).scalar_one()
        if not exists:
            return code


async def authenticate_phone(db, phone: str, code: str, inviter_code: str | None = None):
    """手机号 + 验证码登录（M10 3.1）。

    dev 环境无真实短信网关，接受任意 4–8 位数字作验证码（与 payment_mock 同源约定）。
    生产须替换为真实短信校验。
    """
    if not re.match(r"^1[3-9]\d{9}$", phone or ""):
        raise BizError(40001, "手机号格式不正确")
    if not re.fullmatch(r"\d{4,8}", code or ""):
        raise BizError(40001, "验证码为 4–8 位数字")

    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), phone=phone, role="user", plan="none")
        db.add(user)
        await db.flush()
    if not user.invite_code:
        user.invite_code = await _gen_invite_code(db)

    if inviter_code:
        await share_service.bind_invite(db, inviter_code, user)

    await db.commit()
    await db.refresh(user)
    token = create_access_token(user.id)
    return user, token


async def authenticate_wechat(db, unionid: str, inviter_code: str | None = None):
    """微信 unionid 登录（M10 3.1）。"""
    if not unionid:
        raise BizError(40001, "微信登录缺少 unionid")

    user = (await db.execute(select(User).where(User.unionid == unionid))).scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), unionid=unionid, role="user", plan="none")
        db.add(user)
        await db.flush()
    if not user.invite_code:
        user.invite_code = await _gen_invite_code(db)

    if inviter_code:
        await share_service.bind_invite(db, inviter_code, user)

    await db.commit()
    await db.refresh(user)
    token = create_access_token(user.id)
    return user, token


def user_payload(user: User) -> dict:
    """登录用户资料（脱敏手机号 + 会员信息）。"""
    return {
        "is_guest": False,
        "phone": _mask_phone(user.phone),
        "plan": user.plan,
        "role": user.role,
        "expire_at": _iso(user.plan_expire_at),
        "auto_renew": user.auto_renew,
        "invite_code": user.invite_code,
    }


async def profile(db, owner) -> dict:
    """个人中心资料（M10）。游客返回游客态；登录用户返回脱敏手机号与会员信息。"""
    if owner.is_guest:
        return {"is_guest": True, "plan": "none", "role": "guest"}

    user = await ensure_owner_user(db, owner)
    if not user.invite_code:
        user.invite_code = await _gen_invite_code(db)
        await db.commit()
    return user_payload(user)


async def list_orders(db, owner) -> list[dict]:
    """我的订单（M10）。游客也可查看自己（作为游客身份）下的订单。"""
    user = await ensure_owner_user(db, owner)
    rows = (
        await db.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "order_id": o.id,
            "title": o.title or "",
            "status": o.status,
            "amount": round((o.amount_cents or 0) / 100, 2),
            "created_at": _iso(o.created_at),
        }
        for o in rows
    ]


async def delete_account(db, owner) -> dict:
    """注销账号（M10 3.1）：标记删除，15 日内保留数据供找回，到期由定时任务物理清除隐私字段。"""
    user = await ensure_owner_user(db, owner)
    if user.role in ("guest", "deleted"):
        raise BizError(40101, "该账号无需注销")
    now = _now()
    user.deleted_at = now
    user.purge_at = now + timedelta(days=_PURGE_DAYS)
    user.role = "deleted"
    # 隐私字段（手机号/unionid）按 PRD 在 purge_at 到点后清除，此处仅标记。
    await db.commit()
    return {"deleted_at": _iso(now), "purge_at": _iso(user.purge_at)}


async def logout(db, owner) -> dict:
    """退出登录：服务端无状态（token 留在客户端失效即可），此处仅做记录点。"""
    # 游客态无 token，退出即清本地缓存；登录态退出由前端丢弃 token。
    return {"ok": True}
