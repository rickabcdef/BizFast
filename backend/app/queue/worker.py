"""启动包异步生成消费者（RQ）。

M4-01：启动包(D01–D10) 生成放入队列异步执行，前端轮询真实进度（M4-02）。
worker 可独立扩容：``rq worker default``
"""
import redis
from rq import Queue

from app.core.config import settings
from app.office import generate_deliverable

queue = Queue(settings.rq_queue, connection=redis.from_url(settings.redis_url))


def enqueue_package(order_id: str) -> None:
    """入队一个启动包生成任务。"""
    queue.enqueue("app.queue.worker.run_package", order_id)


# 交付物清单（D01–D10），详见 docs/module-ownership.md
DELIVERABLE_CODES = [f"D{idx:02d}" for idx in range(1, 11)]


def run_package(order_id: str) -> dict:
    """生成十件交付物，返回各文件本地路径（后续由 storage 上传）。"""
    results: dict[str, str] = {}
    for code in DELIVERABLE_CODES:
        # TODO: 从订单/商机上下文取数，调用 office 生成对应文件
        results[code] = generate_deliverable(code, context={"order_id": order_id})
    return results
