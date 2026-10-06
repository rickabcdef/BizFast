"""启动包异步生成消费者（RQ）。

M4-01：启动包(D01–D10) 生成放入队列异步执行，前端轮询真实进度（M4-02）。
worker 可独立扩容：``rq worker default``

注意：真正的生成逻辑在 ``app.services.package.run_generation``，
本模块只提供 RQ 可调用的**同步入口**（RQ 的 job 函数必须是同步的）。
redis / rq 采用惰性导入：本地 inline 模式（无 Redis）下不会因缺依赖而报错。
"""
from __future__ import annotations

import asyncio

# 交付物清单（D01–D10），详见 docs/module-ownership.md
DELIVERABLE_CODES = [f"D{idx:02d}" for idx in range(1, 11)]


def enqueue_package(order_id: str, force: bool = False) -> None:
    """入队一个启动包生成任务（生产环境使用）。"""
    import redis
    from rq import Queue

    from app.core.config import settings

    queue = Queue(settings.rq_queue, connection=redis.from_url(settings.redis_url))
    queue.enqueue("app.queue.worker.run_package", order_id, force)


def run_package(order_id: str, force: bool = False) -> dict:
    """RQ job 入口：同步执行异步生成流程。

    需要 user_id 时从订单反查，与 HTTP 触发路径完全一致。
    force=True 用于「重新生成 / 失败重试」（Package 已处于 generating 状态）。
    """
    from app.core.database import AsyncSessionLocal
    from app.models import Order
    from app.services.package import run_generation

    async def _main() -> None:
        async with AsyncSessionLocal() as db:
            order = await db.get(Order, order_id)
            user_id = order.user_id if order else ""
        if user_id:
            await run_generation(order_id, user_id, force=force)

    asyncio.run(_main())
    return {"order_id": order_id, "codes": DELIVERABLE_CODES}
