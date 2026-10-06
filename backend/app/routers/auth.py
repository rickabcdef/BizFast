"""M10 认证路由 - 负责人 PM

游客创建、手机号验证码登录、JWT 签发/刷新、用户信息、注销账号。
所有端点返回统一响应格式 {code, message, data, request_id}（ADR-006）。
游客可免登录走完诊断与商机（M1-07），付费前才要求登录（M5）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import OwnerContext, current_owner, ensure_owner_user
from app.core.database import get_db
from app.core.errors import BizError
from app.models import Order, User
from app.schemas.common import ok
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["M10 认证"])
# 契约（docs/api-contract.md M10）用 /api/user/* 承载「我的」相关接口，
# 内部实现与 /api/auth/* 共用同一套 service，避免两套逻辑漂移。
user_router = APIRouter(prefix="/api/user", tags=["M10 个人中心"])

_PLAN_LABEL = {
    "none": "游客",
    "single": "单次付费",
    "month": "月度会员",
    "year": "年度会员",
}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _profile(profile: dict) -> dict:
    """把 auth_service 的 profile 映射成前端 UserProfile（types/index.ts）。"""
    return {
        "is_guest": profile.get("role") == "guest",
        "phone": profile.get("phone"),
        "plan": profile.get("plan") or "none",
        "role": profile.get("role"),
        "invite_code": profile.get("invite_code"),
        "expire_at": profile.get("plan_expire_at"),
        "auto_renew": bool(profile.get("auto_renew")),
    }


async def _auth_result(db: AsyncSession, login: dict) -> dict:
    """统一成前端 AuthResult 结构：{token, user}（见 types/index.ts）。"""
    profile = await auth_service.get_user_profile(db, login["user_id"])
    return {
        "token": login["access_token"],
        "refreshToken": login.get("refresh_token"),
        "user_id": login["user_id"],
        "user": _profile(profile),
        "planLabel": _PLAN_LABEL.get(profile.get("plan") or "none", "游客"),
    }


async def _bind_inviter(db: AsyncSession, user, inviter_code: str | None) -> None:
    """登录时顺带绑定邀请人（M8-03，幂等；失败不影响登录主流程）。"""
    if not inviter_code:
        return
    try:
        from app.services import share as share_service

        await share_service.bind_invite(db, inviter_code, user)
    except Exception:  # pragma: no cover - 邀请绑定失败不阻断登录
        pass


@router.post("/guest", summary="创建游客账号")
async def create_guest(request: Request, db: AsyncSession = Depends(get_db)):
    """创建游客账号，返回 JWT。游客可免登录完成诊断与商机浏览。"""
    result = await auth_service.create_guest(db)
    return ok(result, _rid(request))


@router.post("/sms/send", summary="发送短信验证码")
async def send_sms(
    body: auth_service.SmsSendBody, request: Request
):
    """发送短信验证码（开发阶段 mock，固定 123456）。"""
    result = await auth_service.send_sms_code(body.phone)
    return ok(result, _rid(request))


@router.post("/sms/login", summary="手机号验证码登录")
async def sms_login(
    body: auth_service.SmsLoginBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """手机号验证码登录。游客升级为正式用户，已有用户直接登录。"""
    try:
        result = await auth_service.login_with_sms(db, body.phone, body.code)
    except ValueError as e:
        raise BizError(code=40001, message=str(e))
    return ok(result, _rid(request))


@router.post("/refresh", summary="刷新 access_token")
async def refresh_token(
    body: auth_service.RefreshBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """使用 refresh_token 获取新的 access_token。"""
    try:
        result = await auth_service.refresh_access_token(db, body.refresh_token)
    except Exception as e:
        raise BizError(code=40101, message=str(e))
    return ok(result, _rid(request))


@router.get("/me", summary="获取当前用户信息")
async def get_me(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户的信息。需要 Authorization: Bearer <access_token>。"""
    if owner.is_guest or not owner.user_id:
        raise BizError(code=40101, message="请先登录")
    result = await auth_service.get_user_profile(db, owner.user_id)
    return ok(result, _rid(request))


@router.delete("/me", summary="注销账号")
async def delete_me(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """注销当前账号（M10-08）。15 天内清除隐私数据，立即清除登录态。"""
    if owner.is_guest or not owner.user_id:
        raise BizError(code=40101, message="请先登录")
    result = await auth_service.delete_account(db, owner.user_id)
    return ok(result, _rid(request))


# ──────────────────────────────────────────────
#  契约别名（docs/api-contract.md M10：/api/auth/login · /api/auth/wechat · /api/user/*）
#  前端仓库（services/repo.ts）按契约调用这些路径，这里补齐，避免两处契约不一致。
# ──────────────────────────────────────────────
@router.post("/login", summary="手机号验证码登录（契约路径）")
async def login(
    body: auth_service.PhoneLoginBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """手机号 + 验证码登录，返回 {token, user}（M10 3.1）。"""
    if not body.phone or not body.code:
        raise BizError(code=40001, message="请填写手机号与验证码")
    try:
        login_info = await auth_service.login_with_sms(db, body.phone, body.code)
    except ValueError as e:
        raise BizError(code=40001, message=str(e))

    user = (await db.execute(select(User).where(User.id == login_info["user_id"]))).scalar_one_or_none()
    if user is not None:
        await _bind_inviter(db, user, body.inviterCode)
    return ok(await _auth_result(db, login_info), _rid(request))


@router.post("/wechat", summary="微信 unionid 登录（契约路径）")
async def wechat_login(
    body: auth_service.WechatLoginBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """微信 unionid 登录（网页端用占位 unionid），返回 {token, user}。"""
    unionid = (body.unionid or "").strip() or f"web-{uuid.uuid4().hex[:12]}"
    try:
        login_info = await auth_service.login_with_wechat(db, unionid)
    except ValueError as e:
        raise BizError(code=40001, message=str(e))
    return ok(await _auth_result(db, login_info), _rid(request))


@user_router.get("/me", summary="获取当前用户信息（契约路径）")
async def user_me(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """当前登录用户资料（M10 3.1），供个人中心展示会员与邀请信息。"""
    if owner.is_guest or not owner.user_id:
        raise BizError(code=40101, message="请先登录")
    try:
        profile = await auth_service.get_user_profile(db, owner.user_id)
    except ValueError as e:
        raise BizError(code=40101, message=str(e))
    return ok(_profile(profile), _rid(request))


@user_router.get("/orders", summary="我的订单列表（契约路径）")
async def user_orders(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的全部订单（按创建时间倒序），供个人中心「我的订单」展示。"""
    user = await ensure_owner_user(db, owner)

    result = await db.execute(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
    )
    orders = list(result.scalars().all())

    # 订单标题：优先用关联商机名，否则用方案名，保证列表可读
    from app.data.opportunities import OPPORTUNITIES

    opp_titles = {o.get("id"): o.get("title", "") for o in OPPORTUNITIES}
    plan_label = {"single": "单次启动包", "month": "月度会员", "year": "年度会员"}

    items = []
    for o in orders:
        opp_title = opp_titles.get(o.match_id or "", "")
        title = f"{opp_title}·启动包" if opp_title else plan_label.get(o.plan, "支付订单")
        items.append({
            "order_id": o.id,
            "title": title,
            "plan": o.plan,
            "status": o.status,
            "amount": round((o.amount or 0) / 100, 2),
            "amount_cents": o.amount or 0,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return ok(items, _rid(request))


@user_router.post("/logout", summary="退出登录（契约路径）")
async def user_logout(request: Request):
    """退出登录：JWT 无状态，前端清除本地 token 即可，这里返回确认结果。"""
    return ok({"ok": True, "message": "已退出登录"}, _rid(request))


@user_router.delete("/account", summary="注销账号（契约路径）")
async def user_delete_account(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """注销账号（M10-08）：15 天内清除隐私数据，立即清除登录态。"""
    if owner.is_guest or not owner.user_id:
        raise BizError(code=40101, message="请先登录")
    try:
        result = await auth_service.delete_account(db, owner.user_id)
    except ValueError as e:
        raise BizError(code=40101, message=str(e))
    return ok(result, _rid(request))
