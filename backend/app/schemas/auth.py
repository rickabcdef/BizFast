"""D 端鉴权/账号 schema（M10 账号体系 / M1 首屏配置）。对外统一 camelCase。"""
from __future__ import annotations

from app.schemas.common import CamelModel


class AuthLoginIn(CamelModel):
    """手机号 + 验证码登录（M10 3.1）。dev 环境验证码为任意 4–8 位数字（无真实短信网关）。"""

    phone: str
    code: str
    inviterCode: str | None = None


class WechatLoginIn(CamelModel):
    """微信 unionid 登录（M10 3.1）。"""

    unionid: str
    inviterCode: str | None = None


class BindInviteIn(CamelModel):
    """绑定邀请人（M8-03）。可在注册后单独绑定一次。"""

    inviterCode: str


class AdminLoginIn(CamelModel):
    """运营后台登录（M11）。凭据来自环境变量 ADMIN_USERNAME / ADMIN_PASSWORD。"""

    username: str
    password: str
