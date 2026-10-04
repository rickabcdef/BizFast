"""请求上下文：识别「谁」在调用（登录用户 / 游客），产出统一的 owner_key。

PRD：游客可免登录走完诊断与商机（M1-07），付费前才要求登录（M5）。
M10 鉴权由 D 负责；在 M10 上线前，本模块用 `X-Guest-Token` 维持游客身份，
使 A 的链路可以独立跑通（见 docs/api-contract.md 「游客态」约定）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.models import User


@dataclass
class OwnerContext:
    user_id: str | None
    guest_token: str | None
    owner_key: str
    is_guest: bool

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "guest_token": self.guest_token, "is_guest": self.is_guest}


def current_owner(request: Request) -> OwnerContext:
    """从请求头解析 owner（不访问数据库，纯解析）。"""
    authorization = request.headers.get("Authorization")
    user_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = decode_token(authorization.split(" ", 1)[1], ACCESS_TOKEN_TYPE)
        except Exception:
            user_id = None

    guest_token = getattr(request.state, "guest_token", None) or request.headers.get("X-Guest-Token")
    if not guest_token:
        guest_token = uuid.uuid4().hex

    if user_id:
        return OwnerContext(user_id=user_id, guest_token=guest_token, owner_key=f"user:{user_id}", is_guest=False)
    return OwnerContext(
        user_id=None, guest_token=guest_token, owner_key=f"guest:{guest_token}", is_guest=True
    )


async def ensure_owner_user(db: AsyncSession, owner: OwnerContext) -> User:
    """确保存在对应的 User 行（订单表 user_id 为外键）。

    - 已登录：返回既有用户；用户不存在则视为已失效。
    - 游客：按 guest_token 复用或新建一个 role=guest 的用户。
    """
    if owner.user_id:
        user = (await db.execute(select(User).where(User.id == owner.user_id))).scalar_one_or_none()
        if user is not None:
            return user
    user = (
        await db.execute(select(User).where(User.guest_token == owner.guest_token))
    ).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        id=str(uuid.uuid4()),
        guest_token=owner.guest_token,
        role="guest",
        plan="none",
    )
    db.add(user)
    await db.flush()
    return user


def owner_key_for_user(user: User) -> str:
    """由 User 记录反推 owner_key（与 current_owner 的规则保持一致）。

    游客用户用 guest_token，注册用户用 id，保证订单/消息的归属键前后一致。
    """
    if user.guest_token and user.role == "guest":
        return f"guest:{user.guest_token}"
    return f"user:{user.id}"
