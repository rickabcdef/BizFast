"""M4 启动包生成 - 请求/响应模型。

覆盖：生成启动、进度轮询、完整包获取、ZIP 下载、单文件下载、重新生成。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import CamelModel


class PackageGenerateIn(BaseModel):
    """启动包生成请求（需要已支付订单）。"""
    order_id: str


class DeliverableItemOut(CamelModel):
    """单个交付物文件。"""
    code: str           # D01..D10
    name: str           # 可行性评分卡
    file_type: str      # pdf/excel/word/png
    url: str            # 下载/预览 URL
    status: str         # pending/generating/done/failed


class PackageProgressOut(CamelModel):
    """生成进度轮询响应。"""
    order_id: str
    status: str         # generating/delivered/failed
    total: int          # 总数（固定 10）
    done: int           # 已完成数
    percent: int        # 百分比 0–100
    current_item: Optional[str] = None  # 当前正在生成的交付物名称
    items: list[DeliverableItemOut] = []


class PackageResultOut(CamelModel):
    """完整启动包响应。"""
    order_id: str
    status: str         # generating/delivered/failed
    items: list[DeliverableItemOut]
    zip_url: Optional[str] = None
    retry_count: int = 0
    delivered_at: Optional[str] = None


class RegenerateOut(CamelModel):
    """重新生成响应。"""
    order_id: str
    message: str
