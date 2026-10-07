"""M11 运营管理后台 - 请求/响应模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.schemas.common import CamelModel


# ─── 登录 ───

class AdminLoginStep1In(BaseModel):
    username: str
    password: str

class AdminLoginStep1Out(CamelModel):
    need_totp: bool
    totp_hint: str = ""

class AdminLoginStep2In(BaseModel):
    username: str
    totp: str

class AdminSessionOut(CamelModel):
    token: str
    name: str
    username: str
    role: str
    login_at: str


# ─── 看板 ───

class DashboardKpisOut(CamelModel):
    diagnose_count: int = 0
    pay_count: int = 0
    revenue_yuan: float = 0
    conversion_rate: str = "0%"
    package_done_rate: str = "0%"
    refund_rate: str = "0%"
    avg_order_yuan: str = "0"

class DashboardTrendItem(CamelModel):
    label: str
    orders: int = 0
    revenue: float = 0

class DashboardOut(CamelModel):
    kpis: DashboardKpisOut
    trend: list[DashboardTrendItem] = []
    refresh_at: str = ""


# ─── 用户管理 ───

class AdminUserOut(CamelModel):
    id: str
    phone: str
    nickname: str = ""
    city: str = ""
    member_status: str = "none"
    member_label: str = "游客"
    order_count: int = 0
    total_spend_yuan: float = 0
    created_at: str = ""
    risk_flag: bool = False
    source: str = ""
    # M0-04（V5.0）：后台可查任意用户的邀请来源（邀请人手机号，已脱敏）
    inviter_phone: str = ""

class AdminUserDetailOut(CamelModel):
    user: AdminUserOut
    orders: list[dict] = []
    packages: list[dict] = []


# ─── 订单管理 ───

class AdminOrderOut(CamelModel):
    id: str
    user_id: str = ""
    user_phone: str = ""
    plan: str = ""
    plan_name: str = ""
    amount_yuan: float = 0
    status: str = ""
    status_label: str = ""
    channel: str = ""
    created_at: str = ""
    paid_at: Optional[str] = None
    refund_requested: bool = False
    refund_reason: Optional[str] = None
    # M2-05（V5.0）：交付物是否已被下载 —— 已下载的订单退款需人工审核
    downloaded: bool = False
    abnormal: bool = False
    abnormal_type: Optional[str] = None
    # M2-03（V5.0）：异常订单是否已被人工标记处理（处理后不再红色高亮）
    abnormal_handled: bool = False

class RefundActionIn(BaseModel):
    action: str  # approve / reject
    reason: Optional[str] = None


class OrderResolveIn(BaseModel):
    """M2-03（V5.0）：人工标记异常订单已处理。"""

    note: Optional[str] = None


class OrderResolveOut(CamelModel):
    order_id: str
    handled: bool = True
    message: str = ""

class RefundActionOut(CamelModel):
    order_id: str
    status: str
    message: str

class OrderResolveIn(BaseModel):
    note: Optional[str] = None

class OrderResolveOut(CamelModel):
    order_id: str
    handled: bool = True
    message: str = ""


# ─── 商机库管理 ───

class AdminOpportunityOut(CamelModel):
    id: str
    title: str
    category: str = ""
    city: str = ""
    capital_min: int = 0
    capital_max: int = 0
    payback_months: int = 0
    margin_percent: int = 0
    difficulty_stars: int = 1
    source: str = ""
    status: str = "pending"
    status_label: str = "待审核"
    on_shelf: bool = False
    created_at: str = ""

class OpportunitySaveIn(CamelModel):
    id: Optional[str] = None
    title: str = ""
    category: str = "未分类"
    city: str = "全国"
    capital_min: int = 0
    capital_max: int = 0
    payback_months: int = 0
    margin_percent: int = 0
    difficulty_stars: int = 1

class OpportunityImportIn(BaseModel):
    """批量导入商机：items 为待入库的商机数组（CSV/Excel 解析后由前端提交）。"""
    items: list[dict] = []

class OpportunityShelfIn(BaseModel):
    on_shelf: bool

class OpportunityReviewIn(BaseModel):
    action: str  # approve / reject
    reason: Optional[str] = None


# ─── 提示词配置 ───

class PromptVersionOut(CamelModel):
    version: int
    content: str
    model: str
    updated_at: str
    operator: str

class PromptItemOut(CamelModel):
    key: str
    name: str
    content: str
    model: str
    updated_at: str
    versions: list[PromptVersionOut] = []

class PromptSaveIn(CamelModel):
    content: Optional[str] = None
    model: Optional[str] = None

class PromptRollbackIn(BaseModel):
    version: int


# ─── 内容审核 ───

class ReviewItemOut(CamelModel):
    id: str
    type: str = ""
    content: str = ""
    result: Optional[str] = None
    status: str = "pending"
    status_label: str = "待审核"
    reason: Optional[str] = None
    appeal: bool = False
    appeal_reason: Optional[str] = None
    created_at: str = ""

class ReviewActionIn(BaseModel):
    action: str  # pass / reject
    reason: Optional[str] = None

class BatchReviewIn(BaseModel):
    ids: list[str]
    action: str  # pass / reject
    reason: Optional[str] = None

class AppealActionIn(BaseModel):
    action: str  # approve / reject


# ─── 权限管理 ───

class RolePermItem(CamelModel):
    key: str
    label: str
    enabled: bool

class RoleItemOut(CamelModel):
    role: str
    name: str
    description: str = ""
    perms: list[RolePermItem] = []

class RoleSaveIn(CamelModel):
    perms: list[RolePermItem]


# ─── 审计日志 ───

class AuditLogOut(CamelModel):
    id: str
    operator: str = ""
    role: str = ""
    action: str = ""
    target: str = ""
    detail: str = ""
    created_at: str = ""


# ─── 运营位 ───

class OpsSlotOut(CamelModel):
    id: str
    name: str
    type: str = "recommend"
    title: str = ""
    content: str = ""
    enabled: bool = False
    start_at: str = ""
    end_at: str = ""
    updated_at: str = ""

class OpsSlotSaveIn(CamelModel):
    name: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    enabled: Optional[bool] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None

class OpsToggleIn(BaseModel):
    enabled: bool


# ─── 分页 ───

class PageOut(CamelModel):
    items: list = []
    total: int = 0
    page: int = 1
    page_size: int = 20
