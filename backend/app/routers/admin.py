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


@router.post("/orders/resolve-abnormal", summary="一键处理全部异常订单（M2-04）")
async def resolve_abnormal_orders(
    body: schemas.OrderResolveIn,
    request: Request,
    session: dict = Depends(require_perm("orders")),
    db: AsyncSession = Depends(get_db),
):
    """M2-04 验收「支持一键处理异常」：真正批量处理，而不是只做筛选。"""
    result = await admin_service.resolve_abnormal_orders(db, session, body.note)
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


@router.post("/orders/{order_id}/resolve", summary="标记异常订单已处理（M2-03）")
async def resolve_order(
    order_id: str,
    body: schemas.OrderResolveIn,
    request: Request,
    session: dict = Depends(require_perm("orders")),
    db: AsyncSession = Depends(get_db),
):
    result = await admin_service.resolve_order(db, session, order_id, body.note)
    return ok(result, _rid(request))


@router.post("/orders/{order_id}/resend", summary="一键补单（M2-03 / M2-04）")
async def resend_order(
    order_id: str,
    request: Request,
    session: dict = Depends(require_perm("orders")),
    db: AsyncSession = Depends(get_db),
):
    """渠道已扣款但回调丢失时主动查单补单；渠道未确认支付则绝不擅自发货。"""
    result = await admin_service.resend_order(db, session, order_id)
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
    # by_alias=True：运营记录统一以 camelCase 落库，与前端 / 后台列表字段一致
    # （snake_case 会写进一个谁都不读的键，导致「改了不生效」）
    data = body.model_dump(exclude_unset=True, by_alias=True)
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
    data = body.model_dump(exclude_unset=True, by_alias=True)
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


@router.get("/opportunities/{opp_id}/versions", summary="商机版本历史（V5.0 M4-04）")
async def get_opportunity_versions(
    opp_id: str,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.get_opportunity_versions(opp_id)
    return ok(result, _rid(request))


@router.post("/opportunities/{opp_id}/rollback", summary="商机一键回滚（V5.0 M4-04）")
async def rollback_opportunity(
    opp_id: str,
    body: schemas.OpportunityRollbackIn,
    request: Request,
    session: dict = Depends(require_perm("opps")),
):
    result = await admin_service.rollback_opportunity(session, opp_id, body.version)
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


@router.post("/prompts/{prompt_key}/test", summary="提示词一键测试（V5.0 M4-06）")
async def test_prompt(
    prompt_key: str,
    request: Request,
    session: dict = Depends(require_perm("prompts")),
):
    result = await admin_service.test_prompt(prompt_key)
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


# ─── V5.0 三块新看板（M4-05 成本监控 / M4-07 转化漏斗 / M4-08 裂变数据） ───

@router.get("/cost-monitor", summary="AI 成本监控（V5.0 M4-05，超 25% 自动告警）")
async def cost_monitor(
    request: Request,
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import ai_cost

    return ok(await ai_cost.cost_monitor(db), _rid(request))


@router.get("/funnel", summary="转化漏斗（V5.0 M4-07，按日/周/月）")
async def conversion_funnel(
    request: Request,
    period: str = Query("day", description="统计周期: day/week/month"),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import funnel as funnel_service

    return ok(await funnel_service.funnel(db, period), _rid(request))


@router.get("/growth", summary="裂变数据看板（V5.0 M4-08，含 K 因子）")
async def growth_board(
    request: Request,
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import share as share_service

    return ok(await share_service.get_share_stats(db), _rid(request))


# ─── V5.0 第 8 章 运营自动化：数据日报 / 告警 ───

@router.get("/daily-reports", summary="每日数据日报列表（第 8 章 8.2，每天 9 点自动生成）")
async def daily_reports(
    request: Request,
    limit: int = Query(30, ge=1, le=180),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    return ok({"items": await automation.list_daily_reports(db, limit)}, _rid(request))


@router.get("/daily-reports/{report_date}", summary="查看指定日期日报（YYYY-MM-DD）")
async def daily_report_detail(
    report_date: str,
    request: Request,
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    row = await automation.get_daily_report(db, report_date)
    if row is None:
        raise BizError(40401, "该日期的日报尚未生成")
    return ok(row, _rid(request))


@router.post("/daily-reports/generate", summary="手动补生成日报（默认昨天）")
async def generate_daily_report(
    request: Request,
    report_date: str | None = Query(None, description="YYYY-MM-DD，留空则统计昨天"),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    report = await automation.build_daily_report(db, report_date)
    status = await automation.push_daily_report(db, report)
    report["pushStatus"] = status
    return ok(report, _rid(request))


@router.get("/alerts", summary="后台告警列表（M2-04 异常订单 / 成本超限）")
async def alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False, alias="unreadOnly"),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    return ok(await automation.list_alerts(db, limit, unread_only), _rid(request))


@router.post("/alerts/scan", summary="立即执行一次异常扫描（M2-04 一键巡检）")
async def scan_alerts(
    request: Request,
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    return ok(await automation.run_alert_scan_job(db), _rid(request))


@router.post("/alerts/read", summary="标记告警已读（不传 id 则全部已读）")
async def read_alerts(
    request: Request,
    alert_id: str | None = Query(None, alias="alertId"),
    session: dict = Depends(require_perm("dashboard")),
    db: AsyncSession = Depends(get_db),
):
    from app.services import automation

    count = await automation.mark_alert_read(db, alert_id)
    return ok({"updated": count}, _rid(request))
