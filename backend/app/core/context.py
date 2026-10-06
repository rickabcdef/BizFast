"""请求上下文：识别「谁」在调用（登录用户 / 游客），产出统一的 owner_key。

PRD：游客可免登录走完诊断与商机（M1-07），付费前才要求登录（M5）。
M10 鉴权由 D 负责；在 M10 上线前，本模块用 `X-Guest-Token` 维持游客身份，
使 A 的链路可以独立跑通（见 docs/api-contract.md 「游客态」约定）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import BizError
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


# M11-07：运营后台四角色（管理员 / 运营 / 客服 / 财务）
ADMIN_ROLES = ("admin", "operator", "support", "finance")

# 角色 → 中文名（审计日志与前端展示共用）
ADMIN_ROLE_NAMES = {
    "admin": "管理员",
    "operator": "运营",
    "support": "客服",
    "finance": "财务",
}


async def require_admin(
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
) -> User:
    """运营后台鉴权依赖（M11）。

    要求：
    1. 已登录（非游客），Bearer 中携带有效 JWT
    2. 用户存在
    3. 用户角色属于后台四角色之一（admin/operator/support/finance）

    返回 User 对象，供后续业务逻辑使用。失败一律抛中文 BizError（ADR-006）。
    """
    if owner.is_guest or not owner.user_id:
        raise BizError(code=40101, message="请先登录管理员账号")

    user = (await db.execute(
        select(User).where(User.id == owner.user_id)
    )).scalar_one_or_none()

    if not user:
        raise BizError(code=40101, message="登录已过期，请重新登录")

    if user.role not in ADMIN_ROLES:
        raise BizError(code=40301, message="当前账号无权限访问运营后台")

    return user


def admin_session(user: User) -> dict:
    """把后台 User 转成服务层的 session 上下文（审计日志需要操作人与角色）。"""
    username = ""
    if user.unionid and user.unionid.startswith("admin:"):
        username = user.unionid.split(":", 1)[1]
    return {
        "id": user.id,
        "username": username,
        "name": _admin_display_name(username, user.role),
        "role": user.role,
    }


def _admin_display_name(username: str, role: str) -> str:
    """后台账号展示名：优先取账号名，其次取角色中文名。"""
    from app.services.admin import MOCK_ACCOUNTS  # 延迟导入，避免循环依赖

    acc = MOCK_ACCOUNTS.get(username)
    if acc:
        return acc["name"]
    return ADMIN_ROLE_NAMES.get(role, role)


async def current_admin(user: User = Depends(require_admin)) -> dict:
    """运营后台会话上下文（dict）：含操作人姓名与角色，供服务层写审计日志。

    路由统一用 `session: dict = Depends(current_admin)`，
    避免各处重复把 User 转成 session。
    """
    return admin_session(user)


def require_perm(perm: str):
    """生成「按角色最小权限」校验依赖（M11-07，越权操作被拦截）。

    注意：本函数**同步**返回一个依赖工厂（不是协程），
    这样 FastAPI 才能把 `require_perm("users")` 的返回值识别为依赖可调用体。
    管理员（admin）默认放行；其余角色按 roles.json 中已启用的权限判断。
    依赖的返回值统一是「后台会话 dict」（供服务层写审计日志）。
    """
    async def _checker(user: User = Depends(require_admin)) -> dict:
        if user.role != "admin":
            from app.services import admin as admin_service

            enabled = await admin_service.role_has_perm(user.role, perm)
            if not enabled:
                raise BizError(code=40301, message="当前角色无此操作权限，请联系管理员")
        return admin_session(user)

    return _checker
