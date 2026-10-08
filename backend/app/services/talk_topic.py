"""V5.0 M5-03 今日谈资卡（免费传播物，P0）。

需求要点：
- 每天一条「同城/本行业赚钱机会速览」卡片，支持一键转发；
- 每日 0 点自动生成更新；每条带来源和日期；
- 单次成本 ≤ 0.03 元（**模板化**，绝不调用大模型）；
- 卡片不带付费引导，只带品牌标识，转发出去不显突兀。

实现：从商机库按「日期 + 城市」做确定性取样（同一天同一城市结果稳定、可复现），
用模板渲染标题与要点，落库后供前台一键转发。
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.data import opp_library
from app.models import TalkTopic
from app.services import ai_cost

logger = logging.getLogger(__name__)

BRAND = "生意快启"
SOURCE = "生意快启 · 商机库（公开案例整理）"
LINES_PER_CARD = 5


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seed(topic_date: str, city: str) -> int:
    raw = f"{topic_date}|{city}".encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:8], 16)


def _pick(topic_date: str, city: str, n: int = LINES_PER_CARD) -> list[dict]:
    """确定性取样：同一天同一城市，取到的商机稳定不变（可复现、便于缓存）。"""
    # 走「有效视图」：后台运营下架 / 新增的商机会影响今日谈资（M4-04）
    pool = opp_library.library()
    if not pool:
        return []
    start = _seed(topic_date, city) % len(pool)
    picked: list[dict] = []
    for i in range(min(n, len(pool))):
        picked.append(pool[(start + i) % len(pool)])
    return picked


def _capital_text(op: dict) -> str:
    lo = op.get("capital_min", 0)
    hi = op.get("capital_max", 0)
    if lo <= 0 and hi <= 0:
        return "启动资金灵活"
    if lo <= 0:
        return f"{hi // 10000 or 1}万以内起步" if hi >= 10000 else f"{hi}元以内起步"
    if hi >= 10000:
        return f"{lo // 10000 or 1}–{max(1, hi // 10000)}万元"
    return f"{lo}–{hi}元"


def _date_cn(topic_date: str) -> str:
    try:
        d = date.fromisoformat(topic_date)
        return f"{d.month}月{d.day}日"
    except ValueError:
        return topic_date


def render_topic(topic_date: str, city: str) -> dict:
    """模板化渲染谈资卡内容（纯模板，零模型成本）。

    版式对齐 UI 切图 17：一条「焦点谈资」（标签 + 标题 + 大数字 + 正文）
    + 若干条「速览」（其余机会一行速读）。
    """
    ops = _pick(topic_date, city)
    if not ops:
        return {
            "topic_date": topic_date, "city": city or "全国", "industry": "综合",
            "title": "今日谈资", "lines": [], "source": SOURCE, "cover_text": "赚钱机会速览",
            "tag": "💰 我算过一笔账", "headline": "今天的赚钱机会正在整理中",
            "highlight_num": "—", "highlight_label": "数据正在更新", "body": "",
        }

    focus = ops[0]
    icon = focus.get("icon", "📌")
    payback = focus.get("payback_months")
    margin = focus.get("margin_pct")
    cap = _capital_text(focus)

    lines = []
    for op in ops[1:]:
        payback_i = op.get("payback_months")
        margin_i = op.get("margin_pct")
        parts = [_capital_text(op)]
        if payback_i:
            parts.append(f"{payback_i} 个月回本")
        if margin_i:
            parts.append(f"毛利 {margin_i}%")
        lines.append(f"{op.get('icon', '📌')} {op.get('title', '小生意')}｜{'｜'.join(parts)}")

    scope_label = f"{city}本地" if city and city != "全国" else "同城"
    headline = f"{focus.get('title', '这个生意')}，现在还值得做"
    body_parts = [focus.get("summary", "")]
    body_parts.append(f"启动资金约 {cap}。")
    if margin:
        body_parts.append(f"公开案例的毛利率普遍在 {margin}% 上下。")
    if payback:
        body_parts.append(f"回本周期多在 {payback} 个月左右。")

    return {
        "topic_date": topic_date,
        "city": city or "全国",
        "industry": "综合",
        "title": f"{_date_cn(topic_date)} · 今天这 {len(ops)} 个{scope_label}赚钱机会值得看一眼",
        "lines": lines,
        "source": SOURCE,
        "cover_text": f"{scope_label}赚钱机会速览",
        "tag": f"{icon} 我算过一笔账",
        "headline": headline,
        "highlight_num": f"{payback} 个月" if payback else cap,
        "highlight_label": f"{focus.get('title', '该项目')}的常见回本周期（公开案例整理）",
        "body": "\n".join(p for p in body_parts if p),
        "stat": {
            "payback_months": payback,
            "margin_pct": margin,
            "capital_text": cap,
            "category": focus.get("category", ""),
        },
    }


async def ensure_today(db, city: str = "全国") -> TalkTopic:
    """确保今天的谈资卡已生成（幂等：已存在直接返回）。"""
    topic_date = _today()
    city = (city or "全国").strip() or "全国"
    existing = (
        await db.execute(
            select(TalkTopic).where(
                TalkTopic.topic_date == topic_date, TalkTopic.city == city
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    content = render_topic(topic_date, city)
    topic = TalkTopic(
        topic_date=topic_date,
        city=city,
        industry=content["industry"],
        title=content["title"],
        lines=json.dumps(content["lines"], ensure_ascii=False),
        content=json.dumps(content, ensure_ascii=False),
        source=content["source"],
        cover_text=content["cover_text"],
    )
    db.add(topic)
    # 模板化成本记账（≤0.03 元/条）
    await ai_cost.record_call(
        db,
        "topic",
        prompt_tokens=120,
        completion_tokens=sum(len(ln) for ln in content["lines"]) // 3 + 50,
        owner_key=None,
        template_mode=True,
        model="template-engine",
    )
    await db.commit()
    await db.refresh(topic)
    logger.info("今日谈资卡已生成：%s %s", topic_date, city)
    return topic


async def run_daily(db) -> list[TalkTopic]:
    """每日 0 点定时任务入口：生成今日谈资卡（全国版 + 有活跃用户的城市版）。"""
    from app.models import DiagnosisTask

    cities = ["全国"]
    try:
        rows = (
            await db.execute(
                select(DiagnosisTask.city).distinct().limit(20)
            )
        ).scalars().all()
        cities += [c for c in rows if c and c not in cities]
    except Exception as exc:  # 城市维度可选，失败不影响全国版
        logger.warning("谈资卡城市维度取样失败：%s", exc)

    made: list[TalkTopic] = []
    for c in cities[:10]:
        try:
            made.append(await ensure_today(db, c))
        except Exception as exc:
            logger.warning("谈资卡生成失败（%s）：%s", c, exc)
    return made


def payload(topic: TalkTopic, share_url: str | None = None) -> dict:
    try:
        lines = json.loads(topic.lines or "[]")
    except json.JSONDecodeError:
        lines = []
    try:
        content = json.loads(topic.content or "{}")
    except json.JSONDecodeError:
        content = {}
    return {
        "id": topic.id,
        "date": topic.topic_date,
        "city": topic.city,
        "industry": topic.industry,
        "title": topic.title,
        "lines": lines,
        "source": topic.source,
        "brand": BRAND,
        "cover_text": topic.cover_text,
        "share_url": share_url,
        # 版式字段（对齐 UI 切图 17：焦点谈资 + 速览）
        "tag": content.get("tag", "💰 我算过一笔账"),
        "headline": content.get("headline", topic.title),
        "highlight_num": content.get("highlight_num", ""),
        "highlight_label": content.get("highlight_label", ""),
        "body": content.get("body", ""),
        "stat": content.get("stat", {}),
        # 合规：谈资卡不带付费引导，只带品牌标识
        "no_paywall": True,
    }


async def today(db, city: str = "全国", share_url: str | None = None) -> dict:
    topic = await ensure_today(db, city)
    return payload(topic, share_url)


async def history(db, days: int = 7, city: str = "全国") -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = (
        await db.execute(
            select(TalkTopic)
            .where(TalkTopic.topic_date >= since, TalkTopic.city == city)
            .order_by(TalkTopic.topic_date.desc())
        )
    ).scalars().all()
    return [payload(t) for t in rows]
