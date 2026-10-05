"""运营管理后台路由 - 负责人 B+D - 对应 m11_admin

目前实现：后台登录（M11 入口，凭据来自环境变量 ADMIN_USERNAME / ADMIN_PASSWORD）。
其余后台接口（仪表盘/用户/订单/商机/提示词/审核/角色/审计）由 B 在 app/services/admin.py 补充。
分享转化概览（M11-D）见 app/routers/share.py 的 /api/admin/share/stats。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BizError
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import AdminLoginIn
from app.schemas.common import ok

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.post("/login", summary="运营后台登录（M11）")
async def admin_login(payload: AdminLoginIn, request: Request, db: AsyncSession = Depends(get_db)):
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise BizError(40101, "账号或密码错误")
    user = (await db.execute(select(User).where(User.role == "admin"))).scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), unionid=f"admin:{payload.username}", role="admin", plan="none", invite_code="ADMIN")
        db.add(user)
        await db.flush()
    token = create_access_token(user.id)
    await db.commit()
    return ok({"token": token, "user": {"role": "admin"}}, _rid(request))
