"""M3 商机匹配 业务逻辑层 - 负责人 A

- M3-01 输出 3 个与用户资金/时间/城市强相关的商机（真实打分排序，不做通用推荐）
- M3-02 每个商机 5 个关键数字，全部说人话
- M3-03 商机详情（投入构成 / 收益测算 / 成本拆解）
- M3-04 每个商机 ≥2 个真实案例（脱敏，标注来源与时间）
- M3-05 每个商机 ≥3 条风险 + 1 条止损建议
- M3-06 收藏与对比
- M3-07 第 4 个锁定商机：详情需付费/会员权益，未解锁返回 40301
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.context import OwnerContext
from app.core.errors import BizError
from app.data import opp_library
from app.data import opportunities as opp_data
from app.models import Favorite, Order, User
from app.services import diagnose as diag

PAID_STATUSES = ("paid", "generating", "delivered")
MEMBER_PLANS = ("month", "year")

DIFFICULTY_LABELS = {
    1: "几乎零门槛",
    2: "简单易上手",
    3: "需要一点经验",
    4: "需要专业能力",
    5: "门槛较高",
}


def _capital_range_label(lo: int, hi: int) -> str:
    if hi <= 10_000:
        return f"{hi / 10_000:.1f}万元以内".replace(".0万", "万")
    mid = (lo + hi) / 2
    if mid < 10_000:
        return f"{mid / 10_000:.1f}万元左右"
    return f"{mid / 10_000:.0f}万元左右"


def _difficulty_label(level: int) -> str:
    return f"{'⭐' * level} {DIFFICULTY_LABELS.get(level, '')}".strip()


def to_out(op: dict, score: int, locked: bool) -> dict:
    """商机卡片（M3-02 五要素数字卡）。"""
    lo, hi = op["capital_min"], op["capital_max"]
    capital_text = _capital_range_label(lo, hi)
    payback_text = f"{op['payback_months']}个月"
    margin_text = f"{op['margin_pct']}%"
    return {
        "id": op["id"],
        "title": op["title"],
        "icon": op["icon"],
        "category": op["category"],
        "rank": 0,
        "recommend_score": score,
        "summary": op["summary"],
        "tags": op["tags"],
        "five_elements": {
            "capital": capital_text,
            "payback": payback_text,
            "margin": margin_text,
            "first_customer": op["first_customer"],
            "difficulty": _difficulty_label(op["difficulty"]),
        },
        "metrics": {
            "capitalAmountYuan": int(round((lo + hi) / 2)),
            "capitalMinYuan": lo,
            "capitalMaxYuan": hi,
            "paybackMonths": op["payback_months"],
            "marginPercent": op["margin_pct"],
            "difficultyStars": op["difficulty"],
            "recommendScore": score,
        },
        "risks": op["risks"],
        "locked": locked,
    }


def to_detail(op: dict, score: int, locked: bool) -> dict:
    data = to_out(op, score, locked)
    data.update(
        {
            "intro": op["intro"],
            "target_customers": op["target_customers"],
            "channels": op["channels"],
            "skill_required": op["skill_required"],
            "cost_breakdown": op["cost_breakdown"],
            "revenue_estimate": op["revenue_estimate"],
            "cases": op["cases"],
            "stop_loss": op["stop_loss"],
            "steps": op["steps"],
        }
    )
    return data


# ---------------------------------------------------------------- 权益判定
async def _resolve_user(db, owner: OwnerContext) -> User | None:
    """只查询、不创建（读取场景不应产生副作用）。"""
    if owner.user_id:
        user = (await db.execute(select(User).where(User.id == owner.user_id))).scalar_one_or_none()
        if user is not None:
            return user
    if owner.guest_token:
        return (
            await db.execute(select(User).where(User.guest_token == owner.guest_token))
        ).scalar_one_or_none()
    return None


async def is_entitled(db, owner: OwnerContext, match_id: str | None) -> bool:
    """是否已解锁：买过该商机的单次包，或持有月/年会员（M5 权益）。"""
    user = await _resolve_user(db, owner)
    if user is not None and user.plan in MEMBER_PLANS:
        return True
    if not user:
        return False
    stmt = select(Order).where(
        Order.user_id == user.id, Order.status.in_(PAID_STATUSES)
    )
    if match_id:
        stmt = stmt.where((Order.match_id == match_id) | (Order.match_id.is_(None)))
    else:
        stmt = stmt.where(Order.match_id.is_(None))
    order = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    return order is not None


# ---------------------------------------------------------------- 匹配列表
async def get_match_list(db, task) -> dict:
    """M3-01 / M3-07：3 个免费商机 + 1 个锁定商机。"""
    result = json.loads(task.result or "{}")
    scores: dict = result.get("scores") or {}
    tags = json.loads(task.tags or "{}")

    ordered: list[tuple[dict, int]] = []
    for opp_id in result.get("opportunity_ids", []):
        op = opp_library.get(opp_id)
        if op:
            ordered.append((op, int(scores.get(opp_id, 0))))

    if len(ordered) < settings.free_opportunity_count + 1:
        # 兜底：结果缺失时按标签实时重算，保证始终能给出 4 张卡片
        ordered = diag.rank_opportunities(tags, task.capital, diag.task_extra(task))

    needed = settings.free_opportunity_count + 1
    if len(ordered) < needed:
        raise BizError(50001)

    locked_op, locked_score = ordered[0]
    free_items = ordered[1 : 1 + settings.free_opportunity_count]

    free = []
    for idx, (op, score) in enumerate(free_items):
        item = to_out(op, score, locked=False)
        item["rank"] = idx + 1
        free.append(item)
    locked = to_out(locked_op, locked_score, locked=True)

    return {
        "task_id": task.id,
        "city": task.city,
        "city_tier": tags.get("city_level", "tier3"),
        "case_count": opp_data.CASE_COUNT,
        "free": free,
        "locked": locked,
        "total_candidates": len(opp_library.library()),
    }


async def locked_id_for_task(db, task_id: str | None) -> str | None:
    """某次诊断对应的「专属最佳匹配」商机 id（用于详情页权益判定）。"""
    if not task_id:
        return None
    task = await diag.get_task(db, task_id)
    result = json.loads(task.result or "{}")
    ids = result.get("opportunity_ids") or []
    return ids[0] if ids else None


# ---------------------------------------------------------------- 今日限制（V5.0 第 2.3 节）
def _day_start(days_ago: int = 0) -> datetime:
    """当日 0 点（UTC，与 ai_cost / funnel 的统计口径保持一致）。"""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


async def today_quota(db, opportunity_id: str) -> dict:
    """V5.0 第 2.3 节「今日限制」：真实计数的稀缺提示。

    统计口径 = 当天**真实支付成功**（含生成中 / 已交付）的该商机订单数，
    再给出真实的当日剩余份数（总量见配置 `opportunity_daily_limit`）。
    数字全部来自订单表 —— PRD 明确要求「数字必须真实，绝不虚假宣传」。
    """
    limit = int(getattr(settings, "opportunity_daily_limit", 0) or 0)
    start = _day_start(0)
    end = start + timedelta(days=1)
    taken = (
        await db.execute(
            select(func.count(Order.id)).where(
                Order.match_id == opportunity_id,
                Order.status.in_(PAID_STATUSES),
                Order.created_at >= start,
                Order.created_at < end,
            )
        )
    ).scalar_one()
    taken = int(taken or 0)

    if limit > 0:
        remaining = max(0, limit - taken)
        sold_out = remaining == 0
        notice = (
            f"今日已有 {taken} 位用户获取了这个方向的完整启动包，今日份数已领完，明天 0 点刷新。"
            if sold_out
            else f"今日已有 {taken} 位用户获取了这个方向的完整启动包，今日剩余 {remaining} 份。"
        )
    else:
        remaining = None
        sold_out = False
        notice = f"今日已有 {taken} 位用户获取了这个方向的完整启动包。"

    return {
        "opportunity_id": opportunity_id,
        "today_taken": taken,
        "daily_limit": limit,
        "today_remaining": remaining,
        "sold_out": sold_out,
        "notice": notice,
    }


async def get_detail(db, owner: OwnerContext, opportunity_id: str, task_id: str | None = None) -> dict:
    """M3-03：商机详情。锁定商机未解锁时返回 40301。"""
    op = opp_library.get(opportunity_id)
    if op is None:
        raise BizError(40401, "未找到该商机，请重新诊断")

    locked_id = await locked_id_for_task(db, task_id)
    is_locked = locked_id == opportunity_id

    score = 0
    if task_id:
        task = await diag.get_task(db, task_id)
        result = json.loads(task.result or "{}")
        score = int((result.get("scores") or {}).get(opportunity_id, 0))
        if not score:
            tags = json.loads(task.tags or "{}")
            score = diag.score_opportunity(op, tags, task.capital, diag.task_extra(task))

    if is_locked and not await is_entitled(db, owner, opportunity_id):
        raise BizError(40301)

    data = to_detail(op, score, locked=is_locked)
    # V5.0 第 2.3 节「今日限制」：详情底部稀缺提示（真实计数，不造假）
    data["today"] = await today_quota(db, opportunity_id)
    return data


# ---------------------------------------------------------------- 收藏（M3-06）
async def list_favorites(db, owner: OwnerContext) -> dict:
    """V5.0 M10「收藏的商机」：返回当前用户收藏的商机列表（游客亦可）。

    收藏关系按 owner_key 存储（user_id 或 guest_token），故游客收藏也能看到。
    """
    rows = (
        await db.execute(
            select(Favorite)
            .where(Favorite.owner_key == owner.owner_key)
            .order_by(Favorite.created_at.desc())
        )
    ).scalars().all()

    items = []
    for row in rows:
        op = opp_library.get(row.opportunity_id)
        if op is None:
            continue  # 商机已下架则不展示，避免空卡片
        card = to_out(op, 0, False)
        card["favoritedAt"] = row.created_at.strftime("%Y-%m-%d") if row.created_at else ""
        items.append(card)
    return {"items": items, "total": len(items)}


async def toggle_favorite(db, owner: OwnerContext, opportunity_id: str) -> dict:
    if opp_library.get(opportunity_id) is None:
        raise BizError(40401, "未找到该商机，请重新诊断")
    existing = (
        await db.execute(
            select(Favorite).where(
                Favorite.owner_key == owner.owner_key,
                Favorite.opportunity_id == opportunity_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return {"opportunity_id": opportunity_id, "favorited": False}

    import uuid

    db.add(
        Favorite(
            id=str(uuid.uuid4()), owner_key=owner.owner_key, opportunity_id=opportunity_id
        )
    )
    await db.commit()
    return {"opportunity_id": opportunity_id, "favorited": True}
