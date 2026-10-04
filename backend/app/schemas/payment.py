"""M5 付费与订单 schema（负责人 A）。"""
from __future__ import annotations

from app.schemas.common import CamelModel

PlanName = str  # 非法方案由 service 抛中文 BizError，此处不做 Literal 约束


class PlanOption(CamelModel):
    plan: PlanName
    name: str
    price_cents: int
    price_label: str
    unit_label: str
    highlight: bool
    badge: str
    rights: list[str]


class PaymentCreate(CamelModel):
    # 刻意用 str 而非 Literal：非法方案由 service 抛 BizError(40001, "请选择有效的购买方案")，
    # 给出准确的中文提示，而不是通用的参数校验错误。
    plan: str
    platform: str = "web"
    match_id: str | None = None
    idempotency_key: str | None = None
    # M5-09 优惠券 / 邀请码（不可叠加，同一订单只会核销一张）
    coupon_code: str | None = None
    # M5-08 自动续费意向（仅月/年会员有效；不传则不改变当前设置）
    auto_renew: bool | None = None


class PayParams(CamelModel):
    """各端支付参数（M5-04）。mock 模式下为本地模拟支付所需信息。"""

    channel: str
    mode: str  # mock | jsapi | redirect | qrcode | iap
    order_id: str
    amount_cents: int
    qr_content: str | None = None
    redirect_url: str | None = None
    prepay_id: str | None = None
    notice: str


class RiskInfo(CamelModel):
    """M5-10 风控提示：命中只进人工审核，不静默拦截。"""

    flagged: bool
    signal: str | None = None
    label: str = ""
    notice: str = ""


class PaymentCreateOut(CamelModel):
    order_id: str
    plan: PlanName
    amount_cents: int
    amount_label: str
    original_cents: int
    original_label: str
    discount_cents: int
    discount_label: str
    coupon_code: str | None
    channel: str
    status: str
    pay_params: PayParams
    reused: bool
    risk: RiskInfo


class TimelineItem(CamelModel):
    status: str
    label: str
    at: str | None
    done: bool
    active: bool


class OrderOut(CamelModel):
    id: str
    plan: PlanName
    plan_name: str
    amount_cents: int
    amount_label: str
    original_cents: int
    original_label: str
    discount_cents: int
    discount_label: str
    coupon_code: str | None
    platform: str
    channel: str
    status: str
    status_label: str
    match_id: str | None
    package_id: str | None
    package_status: str | None
    created_at: str | None
    paid_at: str | None
    generating_at: str | None
    delivered_at: str | None
    refunded_at: str | None
    closed_at: str | None
    timeline: list[TimelineItem]
    can_refund: bool
    refund_deadline: str | None
    risk: RiskInfo


class RefundCreate(CamelModel):
    order_id: str
    reason: str | None = None


class RefundOut(CamelModel):
    order_id: str
    status: str
    status_label: str
    refunded_at: str | None
    message: str


class PaymentCallbackOut(CamelModel):
    order_id: str
    status: str
    status_label: str
    duplicated: bool
    message: str


# ---------------------------------------------------------------- M5-09 优惠券
class CouponValidateIn(CamelModel):
    code: str
    plan: str = "single"


class CouponValidateOut(CamelModel):
    code: str
    kind: str
    title: str
    discount_cents: int
    discount_label: str
    original_cents: int
    original_label: str
    final_cents: int
    final_label: str
    rules: str
    notice: str


class CouponItem(CamelModel):
    code: str
    kind: str
    title: str
    discount_type: str
    value: int
    discount_label: str
    plan_scope: str
    plan_scope_label: str
    min_amount: int
    usable: bool
    reason: str
    expires_at: str | None


# ---------------------------------------------------------------- M5-08 自动续费
class SubscriptionUpdate(CamelModel):
    auto_renew: bool


class SubscriptionOut(CamelModel):
    plan: str
    plan_name: str
    is_member: bool
    auto_renew: bool
    renewable: bool
    expire_at: str | None
    days_left: int | None
    renew_at: str | None
    renew_notice_days: int
    notice: str
    price_cents: int
    price_label: str
    message: str | None = None
