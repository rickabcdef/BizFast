"""V5.0 第 7 章：AI 成本控制（六道闸门）与成本记账 - 支撑 M4-05 成本监控看板。

六道闸门（研发必须全部实现）：
1. 模型路由：默认走轻档模型（light），效果不达标才升级 mid/top；
2. 全链路缓存：诊断结果 24h 缓存 + 模板缓存，缓存命中价低至未命中价 1/25；
3. 模板化交付：10 件交付物中 7 件模板填充 + 3 件 AI 实时生成；
4. 轮数上限：诊断 ≤8 轮、启动包 ≤25 轮、AI 教练 ≤10 轮；
5. 多模态限额：生图按张扣额度，视频/数字人仅作增值加购；
6. 预算熔断：用户级/项目级/密钥级三重上限，触及后自动降级到模板模式（不拒绝服务）。

成本红线（第 7.1）：免费诊断 ≤0.05 元 / 开业礼包 ≤3.5 元 / 月卡 ≤13 元/月 / 年卡 ≤110 元/年；
运营后台实时监控 AI 成本占收入比，超过 25% 自动告警。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.models import AiCostLog, Order

logger = logging.getLogger(__name__)

# 模型档位单价（分 / 1K tokens）——国产小参数模型起步，绝不一上来就跑最贵模型
# 同一代模型价差可达 100 倍，故轻档默认路由是毛利率的第一道保险。
MODEL_PRICE_CENTS_PER_1K = {
    "light": {"in": 1.5, "out": 6.0},
    "mid": {"in": 6.0, "out": 18.0},
    "top": {"in": 24.0, "out": 90.0},
}

# 缓存命中按未命中价 1/25 计（第 7.2 全链路缓存）
CACHE_DISCOUNT = 1 / 25

# 各档位 AI 成本上限（分）——预算熔断的判定基线
PLAN_BUDGET_CENTS = {
    "none": lambda: settings.ai_budget_free_cents,
    "single": lambda: settings.ai_budget_single_cents,
    "month": lambda: settings.ai_budget_month_cents,
    "year": lambda: settings.ai_budget_year_cents,
}

# 轮数上限（第 7.2 闸门 4）
MAX_ROUNDS = {
    "diagnose": lambda: settings.ai_max_rounds_diagnose,
    "package": lambda: settings.ai_max_rounds_package,
    "coach": lambda: settings.ai_max_rounds_coach,
}


def model_tier() -> str:
    """闸门 1：默认轻档模型。"""
    return getattr(settings, "ai_model_tier", "light") or "light"


def estimate_tokens(text: str | None) -> int:
    """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）。

    无真实模型 Key 时，这是成本核算的唯一依据，故对中英混排取折中系数。
    """
    if not text:
        return 0
    # 中文按 1.5 字/token，其它字符按 4 字符/token
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cn
    return int(cn / 1.5) + int(other / 4) + 1


def compute_cost_cents(
    tier: str, prompt_tokens: int, completion_tokens: int, cache_hit: bool = False
) -> int:
    """折算成本（分），四舍五入取整；不足 1 分按 1 分计（便于看板呈现）。"""
    price = MODEL_PRICE_CENTS_PER_1K.get(tier, MODEL_PRICE_CENTS_PER_1K["light"])
    raw = (prompt_tokens / 1000.0) * price["in"] + (completion_tokens / 1000.0) * price["out"]
    if cache_hit:
        raw *= CACHE_DISCOUNT
    cents = int(round(raw))
    if raw > 0 and cents == 0:
        cents = 1
    return max(0, cents)


def max_rounds(feature: str) -> int:
    fn = MAX_ROUNDS.get(feature)
    return fn() if fn else settings.ai_max_rounds_package


def check_rounds(feature: str, planned_rounds: int) -> dict:
    """闸门 4：轮数上限。**真正拦截**，不只是配置。

    诊断 ≤8 轮 / 启动包 ≤25 轮 / AI 教练 ≤10 轮（第 7.2）。
    计划轮数超过上限时返回 allow_ai=False，调用方必须降级到模板模式，
    而不是把超长智能体任务直接放出去烧钱。
    """
    limit = max_rounds(feature)
    if planned_rounds > limit:
        logger.warning(
            "轮数上限闸门触发：feature=%s planned=%s > limit=%s，降级模板模式",
            feature,
            planned_rounds,
            limit,
        )
        return {
            "allow_ai": False,
            "template_mode": True,
            "limit": limit,
            "planned": planned_rounds,
            "capped_rounds": limit,
            "reason": f"{feature} 计划轮数 {planned_rounds} 超过上限 {limit}，已降级模板模式",
        }
    return {
        "allow_ai": True,
        "template_mode": False,
        "limit": limit,
        "planned": planned_rounds,
        "capped_rounds": planned_rounds,
        "reason": "",
    }


def plan_budget_cents(plan: str) -> int:
    fn = PLAN_BUDGET_CENTS.get(plan or "none")
    return fn() if fn else settings.ai_budget_free_cents


async def spent_cents(db, owner_key: str | None, since: datetime | None) -> int:
    """统计某用户（或全局，owner_key=None）自 since 起的 AI 成本合计（分）。"""
    stmt = select(func.coalesce(func.sum(AiCostLog.cost_cents), 0))
    if owner_key:
        stmt = stmt.where(AiCostLog.owner_key == owner_key)
    if since is not None:
        stmt = stmt.where(AiCostLog.created_at >= since)
    return int((await db.execute(stmt)).scalar_one() or 0)


async def check_budget(db, owner_key: str | None, plan: str, feature: str) -> dict:
    """闸门 6：预算熔断。触及用户级/项目级上限时自动降级模板模式（不拒绝服务）。

    返回 {allow_ai, template_mode, reason, spent_cents, budget_cents}
    - allow_ai=False 时调用方应改用模板/规则引擎，而不是抛错给用户。
    """
    now = datetime.now(timezone.utc)
    window = now - timedelta(days=1 if plan in ("none", "single") else 30)
    budget = plan_budget_cents(plan)
    spent = await spent_cents(db, owner_key, window)

    if budget and spent >= budget:
        logger.warning("AI 预算熔断触发，降级模板模式：owner=%s plan=%s spent=%s/%s", owner_key, plan, spent, budget)
        return {
            "allow_ai": False,
            "template_mode": True,
            "reason": "已达本档 AI 成本上限，自动切换模板模式，服务不中断",
            "spent_cents": spent,
            "budget_cents": budget,
        }
    return {
        "allow_ai": True,
        "template_mode": False,
        "reason": "",
        "spent_cents": spent,
        "budget_cents": budget,
    }


async def record_call(
    db,
    feature: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    *,
    tier: str | None = None,
    owner_key: str | None = None,
    order_id: str | None = None,
    cache_hit: bool = False,
    template_mode: bool = False,
    rounds: int = 0,
    model: str = "",
) -> AiCostLog:
    """记一笔 AI 成本流水（第 7.2 闸门落地数据）。"""
    t = tier or model_tier()
    log = AiCostLog(
        owner_key=owner_key,
        order_id=order_id,
        feature=feature,
        model=model or f"{t}-default",
        tier=t,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_cents=compute_cost_cents(t, prompt_tokens, completion_tokens, cache_hit),
        cache_hit=cache_hit,
        template_mode=template_mode,
        rounds=rounds,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    return log


async def record_ai_call(
    db,
    feature: str,
    prompt: str,
    completion: str | None,
    *,
    owner_key: str | None = None,
    order_id: str | None = None,
    cache_hit: bool = False,
    template_mode: bool = False,
    rounds: int = 0,
) -> AiCostLog:
    """按原文自动估算 token 并记账（无真实模型时的主要入口）。"""
    return await record_call(
        db,
        feature,
        prompt_tokens=estimate_tokens(prompt),
        completion_tokens=estimate_tokens(completion),
        owner_key=owner_key,
        order_id=order_id,
        cache_hit=cache_hit,
        template_mode=template_mode,
        rounds=rounds,
    )


async def record_template_deliverable(
    db, order_id: str, owner_key: str | None, code: str, chars: int = 0
) -> AiCostLog:
    """闸门 3：模板化交付的成本也如实记账（模板填充成本极低）。

    7 件交付物走模板填充，只有 3 件走 AI 实时生成 —— 这是把模型成本压到
    总成本 10% 以内的关键，故模板成本必须可见、可核算。
    """
    prompt_tokens = 120  # 模板变量注入的固定开销
    completion_tokens = max(50, int(chars / 3))  # 渲染出的内容量级
    return await record_call(
        db,
        "package",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        owner_key=owner_key,
        order_id=order_id,
        template_mode=True,
        model="template-engine",
    )


# ---------------------------------------------------------------- M4-05 成本监控看板
def _day_start(days_ago: int = 0) -> datetime:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=days_ago)


async def _revenue_cents(db, since: datetime) -> int:
    """统计自 since 起的已支付订单金额（分）——成本占收入比的分母。"""
    stmt = select(func.coalesce(func.sum(Order.amount), 0)).where(
        Order.paid_at >= since,
        Order.status.in_(["paid", "generating", "delivered", "refunded"]),
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def cost_monitor(db) -> dict:
    """M4-05：实时显示当日/当月 Token 消耗量、成本金额、成本占收入比；超阈值告警。

    返回：today / month 两块 + 按模型与按功能的成本分布 + 告警位。
    """
    today_start = _day_start(0)
    month_start = _day_start(30)
    alert_ratio = float(getattr(settings, "ai_cost_alert_ratio", 0.25))

    async def bucket(since: datetime) -> dict:
        rows = (
            await db.execute(
                select(
                    func.coalesce(func.sum(AiCostLog.total_tokens), 0),
                    func.coalesce(func.sum(AiCostLog.cost_cents), 0),
                    func.count(AiCostLog.id),
                ).where(AiCostLog.created_at >= since)
            )
        ).one()
        tokens, cents, calls = int(rows[0] or 0), int(rows[1] or 0), int(rows[2] or 0)
        revenue = await _revenue_cents(db, since)
        ratio = round(cents / revenue, 4) if revenue else 0.0
        return {
            "tokens": tokens,
            "cost_cents": cents,
            "cost_label": f"{cents / 100:.2f}",
            "calls": calls,
            "revenue_cents": revenue,
            "revenue_label": f"{revenue / 100:.2f}",
            "cost_ratio": ratio,
            "alert": bool(revenue > 0 and ratio > alert_ratio),
        }

    today = await bucket(today_start)
    month = await bucket(month_start)

    # 按模型分布（当月）
    by_model_rows = (
        await db.execute(
            select(
                AiCostLog.model,
                func.coalesce(func.sum(AiCostLog.cost_cents), 0),
                func.coalesce(func.sum(AiCostLog.total_tokens), 0),
            )
            .where(AiCostLog.created_at >= month_start)
            .group_by(AiCostLog.model)
            .order_by(func.sum(AiCostLog.cost_cents).desc())
        )
    ).all()
    by_model = [
        {"model": m or "unknown", "cost_cents": int(c or 0), "cost_label": f"{int(c or 0) / 100:.2f}",
         "tokens": int(t or 0)}
        for m, c, t in by_model_rows
    ]

    # 按功能分布（当月）
    by_feature_rows = (
        await db.execute(
            select(
                AiCostLog.feature,
                func.coalesce(func.sum(AiCostLog.cost_cents), 0),
                func.coalesce(func.sum(AiCostLog.total_tokens), 0),
                func.count(AiCostLog.id),
            )
            .where(AiCostLog.created_at >= month_start)
            .group_by(AiCostLog.feature)
            .order_by(func.sum(AiCostLog.cost_cents).desc())
        )
    ).all()
    feature_cn = {
        "diagnose": "商机诊断",
        "package": "启动包生成",
        "coach": "AI 教练",
        "poster": "海报生成",
        "report": "喜报生成",
        "topic": "今日谈资卡",
    }
    by_feature = [
        {
            "feature": f,
            "feature_label": feature_cn.get(f, f),
            "cost_cents": int(c or 0),
            "cost_label": f"{int(c or 0) / 100:.2f}",
            "tokens": int(t or 0),
            "calls": int(n or 0),
        }
        for f, c, t, n in by_feature_rows
    ]

    # 缓存命中率与模板化占比（当月）—— 六道闸门的节流效果
    total_calls = int(
        (await db.execute(
            select(func.count(AiCostLog.id)).where(AiCostLog.created_at >= month_start)
        )).scalar_one() or 0
    )
    cache_hits = int(
        (await db.execute(
            select(func.count(AiCostLog.id)).where(
                AiCostLog.created_at >= month_start, AiCostLog.cache_hit.is_(True)
            )
        )).scalar_one() or 0
    )
    template_cnt = int(
        (await db.execute(
            select(func.count(AiCostLog.id)).where(
                AiCostLog.created_at >= month_start, AiCostLog.template_mode.is_(True)
            )
        )).scalar_one() or 0
    )

    return {
        "today": today,
        "month": month,
        "by_model": by_model,
        "by_feature": by_feature,
        "gates": {
            "model_tier": model_tier(),
            "cache_hit_rate": round(cache_hits / total_calls, 4) if total_calls else 0.0,
            "template_ratio": round(template_cnt / total_calls, 4) if total_calls else 0.0,
            "max_rounds": {
                "diagnose": settings.ai_max_rounds_diagnose,
                "package": settings.ai_max_rounds_package,
                "coach": settings.ai_max_rounds_coach,
            },
        },
        "budget": {
            "free": settings.ai_budget_free_cents,
            "single": settings.ai_budget_single_cents,
            "month": settings.ai_budget_month_cents,
            "year": settings.ai_budget_year_cents,
        },
        "alert_ratio": alert_ratio,
        "alert": bool(today["alert"] or month["alert"]),
        "notice": (
            f"⚠️ AI 成本占收入比已超过 {int(alert_ratio * 100)}%，建议优化模型路由 / 缓存 / 模板比例"
            if (today["alert"] or month["alert"])
            else f"AI 成本占收入比健康（阈值 {int(alert_ratio * 100)}%）"
        ),
    }
