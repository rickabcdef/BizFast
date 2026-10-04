"""M3 商机匹配 schema（负责人 A）。"""
from __future__ import annotations

from app.schemas.common import CamelModel


class FiveElements(CamelModel):
    """M3-02 五要素数字卡（全部说人话，不出现专业术语）。"""

    capital: str  # 启动资金
    payback: str  # 预计回本周期
    margin: str  # 毛利率
    first_customer: str  # 第一个客户在哪
    difficulty: str  # 上手难度


class CaseItem(CamelModel):
    """M3-04 真实案例（脱敏、标注来源与时间）。"""

    title: str
    source: str
    time: str
    highlight: str


class CostItem(CamelModel):
    item: str
    amount: str
    note: str


class RevenueItem(CamelModel):
    item: str
    value: str
    note: str


class OpportunityOut(CamelModel):
    id: str
    title: str
    icon: str
    category: str
    rank: int
    recommend_score: int
    summary: str
    tags: list[str]
    five_elements: FiveElements
    metrics: dict  # 供前端数字跳动动效使用（真实数值）
    risks: list[str]
    locked: bool


class OpportunityDetail(OpportunityOut):
    intro: str
    target_customers: str
    channels: str
    skill_required: str
    cost_breakdown: list[CostItem]
    revenue_estimate: list[RevenueItem]
    cases: list[CaseItem]
    stop_loss: str
    steps: list[str]


class MatchListOut(CamelModel):
    task_id: str
    city: str
    city_tier: str
    case_count: int
    free: list[OpportunityOut]
    locked: OpportunityOut
    total_candidates: int


class FavoriteOut(CamelModel):
    opportunity_id: str
    favorited: bool
