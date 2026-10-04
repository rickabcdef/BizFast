"""BizFast 后端入口。

挂载各模块路由，注册全局异常处理（中文提示，ADR-006），提供健康检查。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import BizError, biz_exception_handler, validation_exception_handler
from app.core.logging import configure_logging
from app.routers import (
    admin,
    auth,
    diagnose,
    games,
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
    # 启动钩子：预热连接池、加载商机库等
    yield
    # 关闭钩子


app = FastAPI(
    title="BizFast API",
    version="0.1.0",
    description="生意快启后端：诊断/匹配/启动包生成/付费/工具/分享/运营后台",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(BizError, biz_exception_handler)
app.add_exception_handler(Exception, validation_exception_handler)

for r in (auth, diagnose, match, package, payment, tools, games, share, notify, admin):
    app.include_router(r.router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "bizfast", "env": settings.app_env}
