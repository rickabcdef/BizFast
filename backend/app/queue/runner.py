"""进程内 / RQ 后台任务运行器。

A 模块（M2 诊断）与 B 模块（M4 生成）共用：
- `inline`：直接把协程交给事件循环（本地无 Redis 时使用），进度真实来自后端状态。
- `rq`：入队 RQ 由独立 worker 消费（生产）。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.core.config import resolved_queue_backend, settings

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def run_coroutine(coro: Coroutine[Any, Any, Any]) -> None:
    """在进程内事件循环里跑一个后台协程（inline 模式）。"""
    task = asyncio.create_task(coro)
    _tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _tasks.discard(t)
        exc = t.exception()
        if exc is not None:  # pragma: no cover - 依赖具体任务
            logger.exception("background task failed: %s", exc)

    task.add_done_callback(_done)


async def await_background(timeout: float = 60.0) -> None:
    """等待所有进程内后台任务结束（测试/调试用）。"""
    if not _tasks:
        return
    await asyncio.wait(set(_tasks), timeout=timeout)


def enqueue_background(coro_factory, *args: Any, rq_func: str | None = None, **kwargs: Any) -> None:
    """按后端选择执行方式。

    - inline：`coro_factory(*args, **kwargs)` 返回协程，直接调度。
    - rq：把 `rq_func`（"module.func"）与参数入队，由 worker 消费。
    """
    if resolved_queue_backend() == "rq" and rq_func:
        try:
            _enqueue_rq(rq_func, *args, **kwargs)
            return
        except Exception as exc:  # Redis 不可用时自动降级，保证不中断用户流程
            logger.warning("RQ 入队失败，降级为进程内执行：%s", exc)
    run_coroutine(coro_factory(*args, **kwargs))


def _enqueue_rq(func_path: str, *args: Any, **kwargs: Any) -> None:
    import redis
    from rq import Queue

    queue = Queue(settings.rq_queue, connection=redis.from_url(settings.redis_url))
    queue.enqueue(func_path, *args, **kwargs)
