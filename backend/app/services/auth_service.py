"""M10 认证服务：游客创建、手机号登录、JWT 签发/刷新、注销。

实现要点：
- 游客可免登录走完诊断与商机（M1-07），付费前才要求登录（M5）
- 短信验证码开发阶段使用 mock（固定值 123456 或日志输出）
- 注销账号 15 天内清除隐私数据（PRD 3.1）
- 手机号登录自动创建或更新用户记录
"""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import settings
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models import User


# --------------- 请求体模型 ---------------
class SmsSendBody(BaseModel):
    phone: str

class SmsLoginBody(BaseModel):
    phone: str
    code: str

class PhoneLoginBody(BaseModel):
    """契约路径 POST /api/auth/login 的请求体（手机号 + 验证码 + 可选邀请码）。"""
    phone: str
    code: str
    inviterCode: str | None = None


class WechatLoginBody(BaseModel):
    """契约路径 POST /api/auth/wechat 的请求体（unionid 登录）。"""
    unionid: str | None = None


class RefreshBody(BaseModel):
    refresh_token: str


def _generate_invite_code() -> str:
    """生成 8 位唯一邀请码（大写字母+数字）。"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def create_guest(db: AsyncSession) -> dict:
    """创建游客账号。

    - 生成唯一 guest_token
    - 创建 role=guest 的 User 记录
    - 签发 access_token 和 refresh_token
    """
    guest_token = uuid.uuid4().hex
    user_id = str(uuid.uuid4())

    user = User(
        id=user_id,
        guest_token=guest_token,
        role="guest",
        plan="none",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # JWT sub 字段存 user_id
    access_token = create_access_token(sub=user_id)
    refresh_token = create_refresh_token(sub=user_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "is_guest": True,
    }


async def send_sms_code(phone: str) -> dict:
    """发送短信验证码（mock 实现）。

    - 生成 6 位验证码
    - 缓存到 Redis/内存，TTL 5 分钟
    - 生产环境应调用真实短信 API
    """
    cache = get_cache()
    # mock 验证码：开发阶段固定为 123456，方便测试
    code = "123456" if settings.app_env == "development" else "".join(
        random.choices(string.digits, k=6)
    )
    await cache.set(f"sms:code:{phone}", code, ttl=300)  # 5 分钟过期
    # 生产环境这里应调用短信服务商 API
    # TODO: 接入真实短信服务（阿里云短信 / 腾讯云短信）
    return {"message": "验证码已发送", "code": code if settings.app_env == "development" else None}


async def login_with_sms(db: AsyncSession, phone: str, code: str) -> dict:
    """手机号验证码登录。

    - 校验验证码（从缓存读取比对）
    - 查找或创建用户（role 从 guest 升级为 user）
    - 签发 access_token 和 refresh_token
    """
    cache = get_cache()
    cached_code = await cache.get(f"sms:code:{phone}")

    if not cached_code or cached_code != code:
        raise ValueError("验证码错误或已过期")

    # 验证码使用后立即删除
    await cache.delete(f"sms:code:{phone}")

    # 查找或创建用户
    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()

    if user is None:
        # 新用户注册
        user = User(
            id=str(uuid.uuid4()),
            phone=phone,
            role="user",
            plan="none",
            invite_code=_generate_invite_code(),
        )
        db.add(user)
    else:
        # 已有用户：如果是游客，升级为正式用户
        if user.role == "guest":
            user.role = "user"
            user.guest_token = None  # 清除游客标识
            if not user.invite_code:
                user.invite_code = _generate_invite_code()

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(sub=user.id)
    refresh_token = create_refresh_token(sub=user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.id,
        "is_guest": user.role == "guest",
    }


async def login_with_wechat(db: AsyncSession, unionid: str, inviter_code: str | None = None) -> dict:
    """微信 unionid 登录（M10 3.1）。

    网页端没有真实微信 SDK，用占位 unionid 走同一套「查找或创建用户」逻辑，
    保证登录后订单 / 消息归属与手机号登录完全一致（多端权益互通）。
    """
    unionid = (unionid or "").strip()
    if not unionid:
        raise ValueError("缺少微信标识")

    user = (await db.execute(select(User).where(User.unionid == unionid))).scalar_one_or_none()

    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            unionid=unionid,
            role="user",
            plan="none",
            invite_code=_generate_invite_code(),
        )
        db.add(user)
    elif user.role == "guest":
        user.role = "user"
        user.guest_token = None
        if not user.invite_code:
            user.invite_code = _generate_invite_code()

    await db.commit()
    await db.refresh(user)

    return {
        "access_token": create_access_token(sub=user.id),
        "refresh_token": create_refresh_token(sub=user.id),
        "user_id": user.id,
        "is_guest": user.role == "guest",
    }


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    """刷新 access_token。

    - 校验 refresh_token 类型和有效期
    - 查找用户（确保未被删除）
    - 签发新的 access_token
    """
    user_id = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    if user is None:
        raise ValueError("用户不存在或已被删除")
    if user.deleted_at is not None:
        raise ValueError("账号已注销")

    new_access_token = create_access_token(sub=user_id)

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,  # 返回原 refresh_token
        "user_id": user_id,
        "is_guest": user.role == "guest",
    }


async def get_user_profile(db: AsyncSession, user_id: str) -> dict:
    """获取用户信息。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    return {
        "user_id": user.id,
        "phone": user.phone,
        "unionid": user.unionid,
        "role": user.role,
        "plan": user.plan,
        "plan_expire_at": user.plan_expire_at.isoformat() if user.plan_expire_at else None,
        "auto_renew": user.auto_renew,
        "invite_code": user.invite_code,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def delete_account(db: AsyncSession, user_id: str) -> dict:
    """注销账号（M10-08）。

    - 标记 deleted_at 和 purge_at（15 天后）
    - 定时任务到 purge_at 时物理清除隐私数据
    - 立即清除登录态（清除 token、游客标识）
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    now = datetime.now(timezone.utc)
    user.deleted_at = now
    user.purge_at = now + timedelta(days=15)
    # 清除登录态
    user.guest_token = None
    user.phone = None
    user.unionid = None

    await db.commit()

    return {
        "user_id": user_id,
        "purge_at": user.purge_at.isoformat(),
        "message": "账号已注销，15 天内将清除所有隐私数据",
    }
