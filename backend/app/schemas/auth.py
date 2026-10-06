"""M10 认证模块：请求/响应模型。

覆盖：游客创建、手机号验证码登录、刷新令牌、用户信息、注销账号。
"""
from datetime import datetime
from typing import Optional

from app.schemas.common import CamelModel


class GuestCreateOut(CamelModel):
    """游客创建成功响应。"""
    access_token: str
    refresh_token: str
    user_id: str
    is_guest: bool = True


class SmsSendIn(CamelModel):
    """发送短信验证码请求。"""
    phone: str


class SmsLoginIn(CamelModel):
    """短信验证码登录请求。"""
    phone: str
    code: str


class TokenOut(CamelModel):
    """登录/刷新成功响应。"""
    access_token: str
    refresh_token: str
    user_id: str
    is_guest: bool


class RefreshIn(CamelModel):
    """刷新令牌请求。"""
    refresh_token: str


class UserProfile(CamelModel):
    """用户信息响应。"""
    user_id: str
    phone: Optional[str] = None
    unionid: Optional[str] = None
    role: str
    plan: str
    plan_expire_at: Optional[datetime] = None
    auto_renew: bool
    invite_code: Optional[str] = None
    created_at: datetime


class AccountDeleteOut(CamelModel):
    """注销账号响应。"""
    user_id: str
    purge_at: datetime
    message: str
