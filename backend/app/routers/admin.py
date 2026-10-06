"""M11 运营管理后台路由（prefix: /api/admin）。

约定：
- 全部端点返回统一信封 {code, message, data, request_id}（ADR-006，全中文提示）。
- 除登录两步外，其余端点均需 `Authorization: Bearer <后台 access_token>`。
- 越权由 `require_admin` / `require_perm` 拦截，操作统一写入审计日志（M11-08）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import require_perm
from app.core.database import get_db
from app.core.errors import BizError
from app.schemas import admin as schemas
from app.schemas.common import ok
from app.services import admin as admin_service

router = APIRouter(prefix="/api/admin", tags=["M11 运营管理后台"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _dump(body) -> dict:
    """把请求模型转成 snake_case dict（只含有值的字段）。"""
    return body.model_dump(exclude_unset=True)


# ─── M11-00 认证（账号密码 + TOTP 二次验证） ───

@router.post("/auth/login", summary="管理员登录第一步（账号密码）")
async def admin_login(body: schemas.AdminLoginStep1In, request: Request):
    result = await admin_service.admin_login_step1(body.username, body.password)
    return ok(result, _rid(request))


@router.post("/auth/verify-2fa", summary="管理员登录第二步（TOTP 验证）")
async def admin_verify_2fa(
    body: schemas.AdminLoginStep2In,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.admin_login_step2(body.username, body.totp, db)
    return ok(result, _rid(request))


# ─── M11-05 数据看板 ───

@router.get("/dashboard", summary="看板指标与趋势（日/周/月）")
async def get_dashboard(
    request: Request,
    granularity: str = Query("day", description="时间粒度: day/week/month"),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_dashboard(db, granularity)
    return ok(result, _rid(request))


# ─── M11-01 用户管理 ───

@router.get("/users", summary="用户列表（分页 / 搜索 / 筛选）")
async def get_users(
    request: Request,
    keyword: Optional[str] = Query(None, description="手机号 / 用户ID"),
    member_status: Optional[str] = Query(None, alias="memberStatus", description="会员等级"),
    source: Optional[str] = Query(None, description="来源渠道"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    session: dict = Depends(require_perm("users")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_users(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        member_status=member_status,
        source=source,
    )
    return ok(result, _rid(request))


@router.get("/users/{user_id}", summary="用户详情（含全部订单与启动包）")
async def get_user_detail(
    user_id: str,
    request: Request,
    session: dict = Depends(require_perm("users")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_user_detail(db, user_id)
    return ok(result, _rid(request))


# ─── M11-02 订单管理 ───

@router.get("/orders", summary="订单列表（异常标红 / 筛选）")
async def get_orders(
    request: Request,
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    abnormal: Optional[bool] = Query(None, description="仅看异常订单"),
    channel: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    session: dict = Depends(require_perm("orders")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_orders(
        db,
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
        abnormal=abnormal,
        channel=channel,
    )
    return ok(result, _rid(request))


@router.put("/orders/{order_id}/refund", summary="处理退款（同意 / 驳回）")
async def process_refund(
    order_id: str,
    body: schemas.RefundActionIn,
    request: Request,
    session: dict = Depends(require_perm("refund")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.process_refund(db, session, order_id, body.action, body.reason)
    return ok(result, _rid(request))


# ─── M11-03 商机库管理 ───

@router.get("/opportunities", summary="商机列表")
async def get_opportunities(
    request: Request,
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    session: dict = Depends(require_perm("opps")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_opportunities(
        page=page, page_size=page_size, status=status, keyword=keyword
    )
    return ok(result, _rid(request))


@router.post("/opportunities", summary="新增商机")
async def create_opportunity(
    body: schemas.OpportunitySaveIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    data = _dump(body)
    data.pop("id", None)
    result = await admin_service.save_opportunity(session, data)
    return ok(result, _rid(request))


@router.put("/opportunities/{opp_id}", summary="编辑商机")
async def update_opportunity(
    opp_id: str,
    body: schemas.OpportunitySaveIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    data = _dump(body)
    data["id"] = opp_id
    result = await admin_service.save_opportunity(session, data)
    return ok(result, _rid(request))


@router.delete("/opportunities/{opp_id}", summary="删除商机")
async def delete_opportunity(
    opp_id: str,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.delete_opportunity(session, opp_id)
    return ok(result, _rid(request))


@router.put("/opportunities/{opp_id}/shelf", summary="商机上下架")
async def toggle_opportunity_shelf(
    opp_id: str,
    body: schemas.OpportunityShelfIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.toggle_opportunity_shelf(session, opp_id, body.on_shelf)
    return ok(result, _rid(request))


@router.post("/opportunities/import", summary="批量导入商机")
async def import_opportunities(
    body: schemas.OpportunityImportIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.import_opportunities(session, body.items)
    return ok(result, _rid(request))


@router.post("/opportunities/{opp_id}/review", summary="审核商机")
async def review_opportunity(
    opp_id: str,
    body: schemas.OpportunityReviewIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.review_opportunity(session, opp_id, body.action, body.reason)
    return ok(result, _rid(request))


# ─── M11-04 提示词配置 ───

@router.get("/prompts", summary="提示词配置列表")
async def get_prompts(
    request: Request,
    session: dict = Depends(require_perm("prompts")),
):
    result = await admin_service.get_prompts(session)
    return ok(result, _rid(request))


@router.put("/prompts/{prompt_key}", summary="保存提示词（自动生成新版本）")
async def save_prompt(
    prompt_key: str,
    body: schemas.PromptSaveIn,
    request: Request,
    session: dict = Depends(require_perm("prompts")),
):
    result = await admin_service.save_prompt(session, prompt_key, _dump(body))
    return ok(result, _rid(request))


@router.get("/prompts/{prompt_key}/history", summary="提示词版本历史")
async def get_prompt_history(
    prompt_key: str,
    request: Request,
    session: dict = Depends(require_perm("prompts")),
):
    data = await admin_service.get_prompts(session)
    prompt = next((p for p in data["items"] if p["key"] == prompt_key), None)
    if not prompt:
        raise BizError(40401, "提示词不存在")
    return ok({"versions": prompt.get("versions", [])}, _rid(request))


@router.post("/prompts/{prompt_key}/rollback", summary="回滚提示词到指定版本")
async def rollback_prompt(
    prompt_key: str,
    body: schemas.PromptRollbackIn,
    request: Request,
    session: dict = Depends(require_perm("prompts")),
):
    result = await admin_service.rollback_prompt(session, prompt_key, body.version)
    return ok(result, _rid(request))


# ─── M11-06 内容审核 ───

@router.get("/reviews", summary="内容审核列表")
async def get_reviews(
    request: Request,
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    session: dict = Depends(require_perm("reviews")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.get_reviews(
        db, page=page, page_size=page_size, status=status, keyword=keyword
    )
    return ok(result, _rid(request))


@router.post("/reviews/{review_id}/action", summary="审核单条内容")
async def review_action(
    review_id: str,
    body: schemas.ReviewActionIn,
    request: Request,
    session: dict = Depends(require_perm("reviews")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.review_content(session, review_id, body.action, body.reason)
    return ok(result, _rid(request))


@router.post("/reviews/batch", summary="批量审核内容")
async def batch_review(
    body: schemas.BatchReviewIn,
    request: Request,
    session: dict = Depends(require_perm("reviews")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.batch_review(session, body.ids, body.action, body.reason)
    return ok(result, _rid(request))


@router.post("/reviews/{review_id}/appeal", summary="处理内容申诉")
async def appeal_review(
    review_id: str,
    body: schemas.AppealActionIn,
    request: Request,
    session: dict = Depends(require_perm("reviews")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.appeal_review(session, review_id, body.action)
    return ok(result, _rid(request))


@router.post("/reviews/{review_id}/offline", summary="违规内容一键下架")
async def force_offline(
    review_id: str,
    request: Request,
    session: dict = Depends(require_perm("reviews")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.force_offline(session, review_id)
    return ok(result, _rid(request))


# ─── M11-07 权限管理 ───

@router.get("/roles", summary="角色权限列表")
async def get_roles(
    request: Request,
    session: dict = Depends(require_perm("roles")),
):
    result = await admin_service.get_roles()
    return ok(result, _rid(request))


@router.put("/roles/{role}", summary="保存角色权限配置")
async def save_role(
    role: str,
    body: schemas.RoleSaveIn,
    request: Request,
    session: dict = Depends(require_perm("roles")),
):
    result = await admin_service.save_role(
        session, role, [p.model_dump() for p in body.perms]
    )
    return ok(result, _rid(request))


# ─── M11-08 审计日志 ───

@router.get("/audit", summary="审计日志列表")
async def get_audit_logs(
    request: Request,
    operator: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    session: dict = Depends(require_perm("audit")),
):
    result = await admin_service.get_audit_logs(
        page=page, page_size=page_size, operator=operator, action=action
    )
    return ok(result, _rid(request))


# ─── M11-10 运营位配置 ───

@router.get("/ops", summary="运营位配置列表")
async def get_ops_slots(
    request: Request,
    session: dict = Depends(require_perm("ops")),
):
    result = await admin_service.get_ops_slots()
    return ok(result, _rid(request))


@router.put("/ops/{slot_id}", summary="保存运营位配置")
async def save_ops_slot(
    slot_id: str,
    body: schemas.OpsSlotSaveIn,
    request: Request,
    session: dict = Depends(require_perm("ops")),
):
    result = await admin_service.save_ops_slot(session, slot_id, _dump(body))
    return ok(result, _rid(request))


@router.put("/ops/{slot_id}/toggle", summary="启用 / 停用运营位")
async def toggle_ops_slot(
    slot_id: str,
    body: schemas.OpsToggleIn,
    request: Request,
    session: dict = Depends(require_perm("ops")),
):
    result = await admin_service.toggle_ops_slot(session, slot_id, body.enabled)
    return ok(result, _rid(request))


# ─── M11-11 数据导出 ───

@router.get("/export/{export_type}", summary="导出数据（users/orders/deliveries/events）")
async def export_data(
    export_type: str,
    request: Request,
    format: str = Query("csv", description="导出格式: csv/json"),
    session: dict = Depends(require_perm("export")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.export_data(session, export_type, format, db)
    return ok(result, _rid(request))
