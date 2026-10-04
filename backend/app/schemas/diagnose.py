"""M2 生意诊断 schema（负责人 A）。"""
from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel


class DiagnoseExtra(CamelModel):
    """M2-07 补充问答（**可选**）。

    三个问题分别对应：有没有相关经验 / 接受实体还是线上 / 最在意投入还是回报。
    用户可整体跳过（`skipped=true` 或干脆不传），跳过不影响后续结果。
    """

    # none 没做过 / some 做过类似的 / pro 做过一样的
    experience: Literal["none", "some", "pro"] | None = None
    # offline 只能做实体的 / online 只能做线上的 / both 都可以
    mode: Literal["offline", "online", "both"] | None = None
    # cost 更在意少投入 / profit 更在意多赚点 / balance 想平衡
    priority: Literal["cost", "profit", "balance"] | None = None
    skipped: bool = False


class DiagnoseCreate(CamelModel):
    """三要素条件（M1 → M2）+ 可选补充问答（M2-07）。"""

    capital: int  # 启动资金，单位：元
    daily_hours: int  # 每日可投入小时数（兼职约 2 / 全职 8+）
    city: str
    extra: DiagnoseExtra | None = None


class DiagnoseTags(CamelModel):
    capital_level: Literal["low", "mid", "high", "ultra"]
    time_level: Literal["part", "full", "flex"]
    city_level: Literal["tier1", "new_tier1", "tier2", "tier3", "tier4"]
    capital_label: str
    time_label: str
    city_label: str
    labels: list[str]
    # M2-07：补充问答带来的偏好标签（跳过时为空）
    preference_labels: list[str] = []


class HeatDirection(CamelModel):
    name: str
    heat: int  # 0–100
    reason: str


class DiagnoseCreateOut(CamelModel):
    task_id: str
    cached: bool
    status: str
    percent: int


class DiagnoseProgress(CamelModel):
    task_id: str
    status: str  # pending/running/ready/failed
    stage: str
    percent: int
    message: str
    stages: list[str]
    done_stages: list[str]


class DiagnoseResult(CamelModel):
    task_id: str
    status: str
    city: str
    tags: DiagnoseTags
    directions: list[HeatDirection]
    heatmap_url: str
    cached: bool
    degraded: bool
    case_count: int
    elapsed_ms: int
    # M2-07：回显用户的补充问答（跳过后为 null）
    extra: DiagnoseExtra | None = None


class ShareCardOut(CamelModel):
    """M2-05 分享卡片：产品名 + 二维码 + 3 个最热方向。"""

    task_id: str
    image_url: str
    title: str
    subtitle: str
    directions: list[HeatDirection]
    qr_content: str
    share_text: str
    share_url: str
