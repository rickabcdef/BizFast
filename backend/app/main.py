"""BizFast 后端入口。

挂载各模块路由，注册全局异常处理（中文提示，ADR-006），提供健康检查。
同时注入 request_id 与游客身份（X-Guest-Token），使游客可免登录走完诊断与商机（M1-07）。
"""
from contextlib import asynccontextmanager
from uuid import uuid4

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.database import Base, engine
from app.core.config import settings
from app.core.errors import BizError, biz_exception_handler, validation_exception_handler
from app.core.logging import configure_logging
from app.routers import (
    admin,
    auth,
    diagnose,
    files,
    games,
    home,
    match,
    notify,
    package,
    payment,
    share,
    tools,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # 本地调试（SQLite）自动建表；生产请使用 Alembic 迁移
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    # M5-09：播种演示优惠码（幂等，不覆盖运营已配置的券）
    try:
        from app.core.database import AsyncSessionLocal
        from app.services import coupon as coupon_service

        async with AsyncSessionLocal() as db:
            await coupon_service.seed_catalog(db)
    except Exception as exc:  # pragma: no cover - 播种失败不应阻断服务启动
        logging.getLogger(__name__).warning("优惠码播种失败：%s", exc)
    yield


app = FastAPI(
    title="BizFast API",
    version="0.2.0",
    description="生意快启后端：诊断/匹配/启动包生成/付费/工具/分享/运营后台",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Guest-Token", "X-Request-Id"],
)

app.add_exception_handler(BizError, biz_exception_handler)
# 必须显式注册：否则 FastAPI 内建的 RequestValidationError 处理器优先，
# 会直出英文 422 detail（ADR-006 禁止英文报错 / 裸错误码）。
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, validation_exception_handler)


@app.middleware("http")
async def identity_middleware(request: Request, call_next):
    """注入 request_id 与游客标识（M1-07：不强制登录、不打断流程）。"""
    request.state.request_id = request.headers.get("X-Request-Id") or uuid4().hex
    guest_token = request.headers.get("X-Guest-Token") or uuid4().hex
    request.state.guest_token = guest_token
    try:
        response = await call_next(request)
    except BizError as exc:  # 中间件层兜底，保证任何异常都是中文提示
        response = JSONResponse(
            status_code=200,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
                "request_id": request.state.request_id,
            },
        )
    response.headers["X-Guest-Token"] = guest_token
    response.headers["X-Request-Id"] = request.state.request_id
    return response


for r in (auth, diagnose, match, package, payment, tools, games, share, notify, files, home, admin):
    app.include_router(r.router)

# M4 的「我的启动包」列表走 /api/packages（无 /package 前缀），单独挂载
app.include_router(package.list_router)
# M10 个人中心走 /api/user/*（契约路径），与 /api/auth/* 共用同一套 service
app.include_router(auth.user_router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "bizfast", "env": settings.app_env}
