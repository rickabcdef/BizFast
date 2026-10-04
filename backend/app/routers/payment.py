"""付费与订单 - 负责人 A - 对应 m5_pay

路由前缀: /api/payment
契约: docs/api-contract.md「M5 付费与订单」
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_owner
from app.core.database import get_db
from app.schemas.common import ok
from app.schemas.payment import CouponValidateIn, PaymentCreate, RefundCreate, SubscriptionUpdate
from app.services import coupon as coupon_service
from app.services import payment as payment_service
from app.services import risk as risk_service

router = APIRouter(prefix="/api/payment", tags=["payment"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _client_ip(request: Request) -> str | None:
    """M5-10 风控需要真实来源 IP；网关下优先取 X-Forwarded-For 首段。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/plans", summary="三档价格锚点（9.9 / 39 / 199）")
async def plans(request: Request):
    return ok({"plans": payment_service.plan_options()}, _rid(request))


@router.post("/create", summary="创建支付订单（幂等 + 券核销 + 风控）")
async def create_payment(
    payload: PaymentCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    return ok(
        await payment_service.create_order(db, owner, payload, client_ip=_client_ip(request)),
        _rid(request),
    )


@router.post("/callback/{channel}", summary="支付渠道回调（幂等，重复回调不重复发货）")
async def payment_callback(
    channel: str,
    request: Request,
    body: dict = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
):
    return ok(await payment_service.handle_callback(db, channel, body), _rid(request))


@router.get("/order/{order_id}", summary="主动查单兜底（M5-06，顺带关闭超时未支付订单）")
async def get_order(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    order = await payment_service.query_order(db, order_id, owner)
    package_id, package_status = await payment_service.package_brief(db, order.id)
    return ok(
        payment_service.order_payload(
            order, package_id=package_id, package_status=package_status
        ),
        _rid(request),
    )


@router.post("/refund", summary="7 天无理由退款（24 小时内到账）")
async def refund(
    payload: RefundCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    result = await payment_service.refund_order(db, owner, payload.order_id, payload.reason)
    return ok(result, _rid(request))


# ---------------------------------------------------------------- M5-09 优惠券 / 邀请码
@router.post("/coupon/validate", summary="校验优惠券/邀请码（不核销，仅预览减免）")
async def validate_coupon(
    payload: CouponValidateIn, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    amount = payment_service.plan_price(payload.plan) or payment_service.plan_price("single")
    result = await coupon_service.validate_coupon(db, owner.owner_key, payload.code, payload.plan, amount)
    return ok(result, _rid(request))


@router.get("/coupons", summary="可用优惠码清单（规则在页面明示）")
async def list_coupons(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(
        {
            "items": await coupon_service.list_available(db, owner.owner_key),
            "rules": coupon_service.RULES_TEXT,
            "hint": coupon_service.demo_codes_hint(),
        },
        _rid(request),
    )


# ---------------------------------------------------------------- M5-08 自动续费
@router.get("/subscription", summary="会员订阅与自动续费状态")
async def get_subscription(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await payment_service.get_subscription(db, owner), _rid(request))


@router.put("/subscription", summary="开启 / 关闭自动续费（关闭即取消，一步到位）")
async def update_subscription(
    payload: SubscriptionUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    return ok(
        await payment_service.update_subscription(db, owner, payload.auto_renew), _rid(request)
    )


@router.post("/subscription/cancel", summary="一键取消自动续费（PRD：不超过 3 步）")
async def cancel_subscription(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await payment_service.cancel_subscription(db, owner), _rid(request))


# ---------------------------------------------------------------- M5-10 风控
@router.get("/risk", summary="查询本人风控状态（透明告知，避免莫名被拦）")
async def risk_overview(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    data = await risk_service.overview(db, owner.owner_key)
    return ok(data, _rid(request))
