"""BizFast 后端入口。

挂载各模块路由，注册全局异常处理（中文提示，ADR-006），提供健康检查。
同时注入 request_id 与游客身份（X-Guest-Token），使游客可免登录走完诊断与商机（M1-07）。
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
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

logger = logging.getLogger(__name__)


async def _ops_automation_loop() -> None:
    """V5.0 第 8 章：运营自动化后台任务（一个人也能跑起来）。

    一个循环里跑三件事，全部幂等、单次失败不影响其它：
    - 每 N 分钟（默认 5）：扫描异常订单 + 成本超限 → 写告警并推送（M2-04）
    - 每天 9 点：生成并推送昨日数据日报（8.2）
    - 每天 10 点：会员到期前 3 天 / 1 天提醒续费（M0-03）
    """
    from app.core.database import AsyncSessionLocal
    from app.services import automation

    scan_minutes = max(1, int(getattr(settings, "admin_abnormal_scan_minutes", 5) or 5))
    report_hour = int(getattr(settings, "admin_daily_report_hour", 9) or 9)
    remind_hour = int(getattr(settings, "admin_renew_remind_hour", 10) or 10)

    last_report_day: str | None = None
    last_remind_day: str | None = None

    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            async with AsyncSessionLocal() as db:
                # 1) 异常订单 / 成本告警（高频）
                try:
                    await automation.run_alert_scan_job(db)
                except Exception as exc:
                    logger.warning("异常扫描任务失败：%s", exc)

                # 2) 数据日报（每天一次，过了设定时间即执行）
                if now.hour >= report_hour and last_report_day != today:
                    try:
                        await automation.run_daily_report_job(db)
                        last_report_day = today
                    except Exception as exc:
                        logger.warning("数据日报任务失败：%s", exc)

                # 3) 会员到期提醒（每天一次）
                if now.hour >= remind_hour and last_remind_day != today:
                    try:
                        await automation.notify_expiring_members(db)
                        last_remind_day = today
                    except Exception as exc:
                        logger.warning("会员到期提醒任务失败：%s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 定时任务永不因单次失败退出
            logger.warning("运营自动化任务异常：%s", exc)

        try:
            await asyncio.sleep(scan_minutes * 60)
        except asyncio.CancelledError:
            raise


async def _daily_talk_topic_loop() -> None:
    """V5.0 M5-03：今日谈资卡每日 0 点自动生成（后续访问走幂等命中，零重复成本）。"""
    from app.core.database import AsyncSessionLocal
    from app.services import talk_topic

    while True:
        try:
            now = datetime.now()
            next_run = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=30, microsecond=0
            )
            await asyncio.sleep(max(60.0, (next_run - now).total_seconds()))
            async with AsyncSessionLocal() as db:
                await talk_topic.run_daily(db)
            logger.info("今日谈资卡定时生成完成")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 定时任务永不因单次失败退出
            logger.warning("今日谈资卡定时生成失败：%s", exc)
            await asyncio.sleep(3600)


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
        logger.warning("优惠码播种失败：%s", exc)

    # V5.0 M5-03：启动即预热今日谈资卡 + 挂起每日 0 点自动生成任务
    talk_task: asyncio.Task | None = None
    try:
        from app.core.database import AsyncSessionLocal
        from app.services import talk_topic

        async with AsyncSessionLocal() as db:
            await talk_topic.run_daily(db)
        talk_task = asyncio.create_task(_daily_talk_topic_loop())
    except Exception as exc:  # pragma: no cover
        logger.warning("今日谈资卡预热失败：%s", exc)

    # V5.0 第 8 章：运营自动化（异常告警 / 每日日报 / 会员到期提醒）
    ops_task: asyncio.Task | None = None
    try:
        ops_task = asyncio.create_task(_ops_automation_loop())
    except Exception as exc:  # pragma: no cover
        logger.warning("运营自动化任务启动失败：%s", exc)

    yield

    for task in (talk_task, ops_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


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
