"""A 模块测试夹具：强制使用本地降级链路（SQLite + 本地存储 + 进程内队列）。

必须在导入 app 之前设置环境变量，因此本文件顶部的 os.environ 赋值先于 app 导入执行。
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)

TEST_DB = "var/test_bizfast.db"
TEST_STORAGE = "var/test_storage"

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{TEST_DB}"
os.environ["REDIS_URL"] = ""
os.environ["QUEUE_BACKEND"] = "inline"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = TEST_STORAGE
os.environ["PAYMENT_MOCK"] = "true"
os.environ["DIAGNOSE_STAGE_MIN_MS"] = "0"
os.environ["DIAGNOSE_MOCK_AI"] = "true"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

GUEST_TOKEN_PREFIX = "test-guest"


@pytest.fixture(scope="session", autouse=True)
def _prepare_env():
    var = BACKEND_DIR / "var"
    var.mkdir(exist_ok=True)
    for target in (BACKEND_DIR / TEST_DB, BACKEND_DIR / TEST_STORAGE):
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    yield
    for target in (BACKEND_DIR / TEST_DB, BACKEND_DIR / TEST_STORAGE):
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()


@pytest.fixture(scope="session")
async def _tables():
    from app.core.database import AsyncSessionLocal
    from app.services import coupon as coupon_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 播种演示优惠码：ASGITransport 不会触发 app lifespan，这里手动执行一次
    async with AsyncSessionLocal() as db:
        await coupon_service.seed_catalog(db)
    yield
    await engine.dispose()


@pytest.fixture
async def client(_tables):
    # 每个用例一个独立游客身份：既贴近真实「一个访客一条链路」，也避免
    # 用例之间因共用同一游客而互相干扰（订单唯一约束、消息未读数等）。
    token = f"{GUEST_TOKEN_PREFIX}-{uuid.uuid4().hex}"
    # M5-10 风控会按 IP 统计「同 IP 下单账号数」，用例间共用同一出口 IP 会互相
    # 触发人工审核。这里给每个用例一个独立 IP，保持用例隔离且贴近真实部署。
    ip = f"10.{(uuid.uuid4().int >> 8) % 250}.{(uuid.uuid4().int >> 16) % 250}.{(uuid.uuid4().int >> 24) % 250}"
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-Guest-Token": token, "X-Forwarded-For": ip},
    ) as c:
        yield c


@pytest.fixture
def drain():
    """等待进程内后台任务（诊断）执行完毕。"""
    from app.queue.runner import await_background

    async def _drain(timeout: float = 60.0) -> None:
        await await_background(timeout)

    return _drain


@pytest.fixture
def login():
    """M0-01（V5.0）：把测试客户端换成「已登录用户」。

    PRD 要求「免费诊断免登录，付费前才触发登录」，因此 `/api/payment/create`
    对游客返回 40101。凡是要下单的用例，先调用本夹具完成一次真实短信登录，
    客户端会就地带上 Authorization 头（游客头保留，便于验证游客数据归集）。
    """
    from app.core.cache import get_cache

    async def _login(c: AsyncClient, phone: str | None = None) -> str:
        ph = phone or f"139{uuid.uuid4().int % 10**8:08d}"
        sent = (await c.post("/api/auth/sms/send", json={"phone": ph})).json()
        assert sent.get("code") == 0, f"发送验证码失败：{sent}"
        # test 环境不回传验证码（防泄露），按真实前端拿不到码的场景手动注入
        await get_cache().set(f"sms:code:{ph}", "123456", ttl=300)
        res = (await c.post("/api/auth/login", json={"phone": ph, "code": "123456"})).json()
        assert res.get("code") == 0, f"登录失败：{res}"
        token = res["data"]["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        return token

    return _login
