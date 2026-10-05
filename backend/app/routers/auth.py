"""账号体系路由 - 负责人 D - 对应 m10_user / m1_home

路由前缀统一 /api（下同含 /auth/* 与 /user/* 与 /home/config），路径见 docs/api-contract.md。
业务逻辑见 app/services/auth.py。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import current_owner
from app.core.database import get_db
from app.schemas.auth import AuthLoginIn, WechatLoginIn
from app.schemas.common import ok
from app.services import auth as auth_service

router = APIRouter(prefix="/api", tags=["auth"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.post("/auth/login", summary="手机号 + 验证码登录（M10 3.1）")
async def login(payload: AuthLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.authenticate_phone(
        db, payload.phone, payload.code, payload.inviterCode
    )
    return ok({"token": token, "user": auth_service.user_payload(user)}, _rid(request))


@router.post("/auth/wechat", summary="微信 unionid 登录（M10 3.1）")
async def wechat_login(payload: WechatLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.authenticate_wechat(
        db, payload.unionid, payload.inviterCode
    )
    return ok({"token": token, "user": auth_service.user_payload(user)}, _rid(request))


@router.get("/user/me", summary="个人中心资料（M10）")
async def user_me(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await auth_service.profile(db, owner), _rid(request))


@router.get("/user/orders", summary="我的订单（M10）")
async def user_orders(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await auth_service.list_orders(db, owner), _rid(request))


@router.post("/user/logout", summary="退出登录（M10）")
async def user_logout(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await auth_service.logout(db, owner), _rid(request))


@router.delete("/user/account", summary="注销账号（M10 3.1，15 日内清隐私数据）")
async def user_delete_account(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await auth_service.delete_account(db, owner), _rid(request))


@router.get("/home/config", summary="首屏配置：资金/时间档位 + 城市枚举版本（M1）")
async def home_config(request: Request):
    return ok(
        {
            "capitals": [
                {"label": "1万以下", "value": 1},
                {"label": "1–5万", "value": 2},
                {"label": "5–20万", "value": 3},
                {"label": "20万以上", "value": 4},
            ],
            "dailyHours": [
                {"label": "兼职（每天约2小时）", "value": 2},
                {"label": "全职（每天8小时以上）", "value": 8},
            ],
            "cityVersion": getattr(settings, "city_list_version", "2026.1"),
        },
        _rid(request),
    )
