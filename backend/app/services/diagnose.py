"""M2 生意诊断 业务逻辑层 - 负责人 A

所有算法/计算/生成逻辑集中在此，禁止各端重复实现。

要点：
- M2-01 条件校验与打标 ≤200ms（纯内存计算）
- M2-02 进度真实：percent 严格等于「已完成阶段数 / 总阶段数」，不造假
- M2-04 30 秒内生成可保存的《机会热度图》（Pillow 真实绘制并落对象存储）
- M2-06 相同条件命中 24h 缓存，不重复消耗算力
- M2-08 主模型不可用自动降级备用模型；双模型不可用则降级本地规则引擎，诊断不中断
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.ai import client as ai_client
from app.core.cache import get_cache
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import BizError
from app.data import cities as city_data
from app.data import opportunities as opp_data
from app.models import DiagnosisTask
from app.queue.runner import run_coroutine
from app.services import ai_cost
from app.storage import get_storage

logger = logging.getLogger(__name__)

# ---- 阶段定义（M2-02「说人话」的进度文案，与 UI 等待页 5 步一致）----
# 案例数必须来自真实案例库（opp_data.CASE_COUNT），PRD 反复强调「数字必须真实，
# 绝不虚假宣传」；此前这里写死 1247，而真实案例只有几十条，属于虚假宣传。
STAGES: list[tuple[str, str]] = [
    ("scan", "正在扫描你所在城市的热门赛道"),
    ("match", f"正在比对 {opp_data.CASE_COUNT} 个真实小生意案例"),
    ("payback", "正在计算回本周期与毛利率"),
    ("cases", "正在筛选真实成功案例"),
    ("heatmap", "正在生成你所在城市的机会热度图"),
]
STAGE_LABELS = [label for _, label in STAGES]

CAPITAL_TIERS: list[tuple[int, int, str, str]] = [
    (0, 10_000, "low", "1 万以下"),
    (10_000, 50_000, "mid", "1–5 万"),
    (50_000, 200_000, "high", "5–20 万"),
    (200_000, 10**12, "ultra", "20 万以上"),
]

MIN_CAPITAL = 1_000
MAX_CAPITAL = 50_000_000
MAX_DAILY_HOURS = 16

# 契约 frontend/src/types/index.ts 中 StartupInput.capital 标注为「档位」，
# 前端首屏（M1）按 M1-03 的四档传 1–4。此处做兼容归一：档位 → 代表金额（元）。
# 1 万以下 / 1–5 万 / 5–20 万 / 20 万以上
CAPITAL_TIER_TO_YUAN = {1: 5_000, 2: 30_000, 3: 120_000, 4: 350_000}


def normalize_capital(value) -> int:
    """档位（1–4）或金额（元）统一归一到「元」。"""
    amount = int(value)
    if 1 <= amount <= 4:
        return CAPITAL_TIER_TO_YUAN[amount]
    return amount


# ---------------------------------------------------------------- 校验与打标
def capital_level(capital: int) -> tuple[str, str]:
    for low, high, level, label in CAPITAL_TIERS:
        if low <= capital < high:
            return level, label
    return "ultra", "20 万以上"


def capital_label(capital: int) -> str:
    return capital_level(capital)[1]


def time_level(daily_hours: int) -> tuple[str, str]:
    if daily_hours <= 4:
        return "part", f"兼职（每天约 {daily_hours} 小时）"
    if daily_hours >= 7:
        return "full", f"全职（每天 {daily_hours} 小时）"
    return "flex", f"弹性（每天 {daily_hours} 小时）"


def validate_input(capital, daily_hours, city) -> tuple[int, int, str]:
    """M2-01：合法性校验。错误统一为中文提示（40001 / 40002）。"""
    if capital is None or daily_hours is None or not str(city or "").strip():
        raise BizError(40001)
    try:
        capital = normalize_capital(capital)
        daily_hours = int(daily_hours)
    except (TypeError, ValueError) as exc:
        raise BizError(40001) from exc
    if capital < MIN_CAPITAL or capital > MAX_CAPITAL:
        raise BizError(40001)
    if daily_hours < 1 or daily_hours > MAX_DAILY_HOURS:
        raise BizError(40001)
    normalized = city_data.normalize_city(city)
    if not normalized:
        raise BizError(40002)
    return capital, daily_hours, normalized


def compute_tags(capital: int, daily_hours: int, city: str, extra: dict | None = None) -> dict:
    """M2-01：生成用户标签（资金等级 / 时间等级 / 城市等级），纯内存计算 ≤200ms。

    M2-07：若用户回答了补充问答，额外产出「偏好标签」；跳过则 preference_labels 为空，
    且**不影响**任何后续结果（PRD 要求可跳过）。
    """
    cap_level, cap_label = capital_level(capital)
    t_level, t_label = time_level(daily_hours)
    c_level = city_data.city_tier(city)
    c_label = city_data.TIER_LABELS[c_level]
    labels = [
        cap_label,
        "兼职" if t_level == "part" else ("全职" if t_level == "full" else "弹性"),
        c_label,
    ]
    return {
        "capital_level": cap_level,
        "time_level": t_level,
        "city_level": c_level,
        "capital_label": cap_label,
        "time_label": t_label,
        "city_label": c_label,
        "labels": labels,
        "preference_labels": preference_labels(extra),
    }


# ---- M2-07 补充问答：选项 → 人话标签 / 打分偏好 ----
EXPERIENCE_LABELS = {"none": "零经验起步", "some": "有相关经验", "pro": "做过同样的生意"}
MODE_LABELS = {"offline": "只做实体", "online": "只做线上", "both": "线上线下都行"}
PRIORITY_LABELS = {"cost": "最在意少投入", "profit": "最在意多赚点", "balance": "想平衡投入与回报"}

# 机会类型 → 线上/线下倾向（用于 M2-07「接受实体还是线上」）
ONLINE_CATEGORIES = {"线上", "内容", "服务"}


def preference_labels(extra: dict | None) -> list[str]:
    """把补充问答翻译成用户能看懂的标签（跳过则返回空列表）。"""
    if not extra or extra.get("skipped"):
        return []
    out: list[str] = []
    if extra.get("experience"):
        out.append(EXPERIENCE_LABELS.get(extra["experience"], ""))
    if extra.get("mode"):
        out.append(MODE_LABELS.get(extra["mode"], ""))
    if extra.get("priority"):
        out.append(PRIORITY_LABELS.get(extra["priority"], ""))
    return [x for x in out if x]


def make_cache_key(capital: int, daily_hours: int, city: str, extra: dict | None = None) -> str:
    """缓存键包含补充问答：不同偏好的用户不应互相命中对方的缓存。"""
    extra_sig = ""
    if extra and not extra.get("skipped"):
        extra_sig = "|".join(
            str(extra.get(k) or "") for k in ("experience", "mode", "priority")
        )
    raw = f"{capital}|{daily_hours}|{city}|{extra_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- 匹配打分（M3 共用）
# 权重分解（合计 100），既满足 PRD「与资金/时间/城市强相关」，又保证同档位下有区分度：
#   资金 34 + 时间 26 + 城市 26 = 86（三大强相关维度，占绝对主导）
#   经营质地 8（回本快 / 毛利高 / 上手易）
#   补充问答偏好 6（M2-07，可选；跳过则取中性值，不改变排序）
W_CAPITAL, W_TIME, W_CITY, W_QUALITY, W_PREFERENCE = 34.0, 26.0, 26.0, 8.0, 6.0

# 可线上化的品类（M2-07「接受实体还是线上」）
ONLINE_CAPABLE = {"新媒体服务", "教育培训"}


def _ramp(value: float, best: float, worst: float) -> float:
    """把指标线性映射到 0–1：`value == best` → 1，`value == worst` → 0。

    best / worst 谁大谁小都支持（回本周期越小越好：best<worst；毛利率越大越好：best>worst），
    统一用下面的斜线公式，不需要两套函数。
    """
    if best == worst:
        return 1.0
    ratio = (value - worst) / (best - worst)
    return max(0.0, min(1.0, ratio))


def _preference_score(op: dict, extra: dict | None) -> float:
    """M2-07 偏好契合度。

    跳过问答时取中性 3 分，保证不同用户分数可比、排序不受影响。
    作答时：经验/回报偏好给正向加分（0–2），经营形态按**硬约束**处理——
    用户说「只能做线上」却给一个必须开实体店的方案是错的，因此不匹配要扣分。
    最终收敛到 [-3.5, 6]。
    """
    if not extra or extra.get("skipped"):
        return W_PREFERENCE / 2

    experience_score = 1.0
    experience = extra.get("experience")
    if experience == "none":
        # 零经验：越简单越好
        experience_score = 2.0 * _ramp(op["difficulty"], best=1, worst=5)
    elif experience == "some":
        experience_score = 2.0 * _ramp(op["difficulty"], best=3, worst=5)

    online_ok = op["category"] in ONLINE_CAPABLE
    mode_score = 1.0
    mode = extra.get("mode")
    if mode == "online":
        mode_score = 2.0 if online_ok else -3.0
    elif mode == "offline":
        mode_score = 2.0 if not online_ok else -3.0

    priority_score = 1.0
    priority = extra.get("priority")
    if priority == "cost":
        # 最在意少投入：启动门槛越低越好
        priority_score = 2.0 * _ramp(op["capital_min"], best=5_000, worst=100_000)
    elif priority == "profit":
        # 最在意回报：毛利率越高越好
        priority_score = 2.0 * max(0.0, min(1.0, (op["margin_pct"] - 25) / 45))

    total = experience_score + mode_score + priority_score
    return max(-3.5, min(W_PREFERENCE, total))


def score_opportunity(op: dict, tags: dict, capital: int, extra: dict | None = None) -> int:
    """商机匹配打分（0–100）。资金/时间/城市三维度强相关（M3-01），
    另叠加「经营质地」与「补充问答偏好」，使同一档位下的多张卡片有可解释的区分度。
    """
    score = 0.0

    # 资金适配（34 分）：区间内按「与需求中位的贴近度」在 27–34 之间浮动；
    # 区间外按距离衰减——这样同档位的不同商机不会齐刷刷拿满分。
    lo, hi = op["capital_min"], op["capital_max"]
    if lo <= capital <= hi:
        mid = (lo + hi) / 2
        span = max(1.0, (hi - lo) / 2)
        closeness = 1 - min(1.0, abs(capital - mid) / span)
        score += W_CAPITAL * (0.8 + 0.2 * closeness)
    else:
        distance = lo - capital if capital < lo else capital - hi
        ratio = min(1.0, distance / max(hi, 1000))
        score += W_CAPITAL * 0.8 * (1 - ratio)

    # 时间适配（26 分）
    need = op["time_requirement"]
    t_level = tags["time_level"]
    if need == "both" or need == t_level:
        score += W_TIME
    elif t_level == "flex":
        score += W_TIME * 0.73
    else:
        score += W_TIME * 0.28

    # 城市适配（26 分）
    tiers = op["city_tiers"]
    c_level = tags["city_level"]
    if c_level in tiers:
        score += W_CITY
    elif c_level == "tier4" and "tier3" in tiers:
        score += W_CITY * 0.73
    elif c_level == "tier1" and "tier2" in tiers:
        score += W_CITY * 0.6
    else:
        score += W_CITY * 0.2

    # 经营质地（8 分）：回本越快、毛利越高、上手越易 → 分越高
    score += 3.0 * _ramp(op["payback_months"], best=3, worst=24)
    score += 3.0 * _ramp(op["margin_pct"], best=70, worst=25)
    score += 2.0 * (1 - (op["difficulty"] - 1) / 4)

    # 补充问答偏好（6 分，M2-07）
    score += _preference_score(op, extra)

    return int(round(max(0.0, min(100.0, score))))


def rank_opportunities(
    tags: dict, capital: int, extra: dict | None = None
) -> list[tuple[dict, int]]:
    """按分数倒序返回全部候选商机（真实打分，不做通用推荐）。"""
    scored = [
        (op, score_opportunity(op, tags, capital, extra)) for op in opp_data.OPPORTUNITIES
    ]
    scored.sort(key=lambda item: (-item[1], item[0]["capital_min"]))
    return scored


def build_directions(tags: dict, ranked: list[tuple[dict, int]], top_n: int = 3) -> list[dict]:
    """M2-04：从匹配结果聚合出最热的 3 个方向（真实来自打分）。"""
    agg: dict[str, float] = {}
    for op, score in ranked[:8]:
        direction = opp_data.CATEGORY_TO_DIRECTION.get(op["category"], op["category"])
        agg[direction] = agg.get(direction, 0.0) + score
    ordered = sorted(agg.items(), key=lambda kv: -kv[1])[:top_n]
    if not ordered:
        return []
    top = ordered[0][1] or 1
    reason_map = dict(opp_data.DIRECTIONS)
    tier_note = city_data.TIER_LABELS[tags["city_level"]]
    return [
        {
            "name": name,
            "heat": int(round(60 + 40 * (value / top))),
            "reason": f"{tier_note}适配：{reason_map.get(name, '与你的资金和时间条件匹配度较高')}",
        }
        for name, value in ordered
    ]


# ---------------------------------------------------------------- 热度图（M2-04）
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
_font_cache: dict[int, object] = {}


def _font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            _font_cache[size] = ImageFont.truetype(path, size)
            return _font_cache[size]
        except Exception:
            continue
    _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def render_heatmap(city: str, tags: dict, directions: list[dict], case_count: int) -> bytes:
    """绘制《你所在城市的机会热度图》（科技风：藏蓝底 + 蓝紫渐变条）。"""
    from PIL import Image, ImageDraw

    w, h = settings.heatmap_width, settings.heatmap_height
    top_color = (15, 23, 42)
    bottom_color = (30, 41, 59)
    img = Image.new("RGB", (w, h), top_color)
    draw = ImageDraw.Draw(img)

    for y in range(h):
        ratio = y / max(1, h - 1)
        color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * ratio) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)

    pad = 80
    white = (255, 255, 255)
    text_dim = (170, 180, 210)
    primary = (22, 93, 255)
    primary_end = (123, 97, 255)

    y = pad + 20
    draw.text((pad, y), f"{city} · 机会热度图", font=_font(58), fill=white)
    y += 84
    draw.text(
        (pad, y),
        f"{tags['capital_label']} · {tags['time_label']} · 已比对 {case_count} 个真实案例",
        font=_font(30),
        fill=text_dim,
    )
    y += 90
    draw.line([(pad, y), (w - pad, y)], fill=(60, 70, 100), width=2)
    y += 60

    draw.text((pad, y), "你最该关注的 3 个方向", font=_font(38), fill=white)
    y += 90

    for idx, direction in enumerate(directions):
        draw.text((pad, y), f"{idx + 1}. {direction['name']}", font=_font(40), fill=white)
        draw.text((w - pad - 110, y), str(direction["heat"]), font=_font(40), fill=(160, 170, 255))
        y += 62

        bar_w = w - pad * 2
        bar_h = 28
        draw.rounded_rectangle([pad, y, pad + bar_w, y + bar_h], radius=14, fill=(35, 45, 70))
        fill_w = max(40, int(bar_w * direction["heat"] / 100))
        for x in range(fill_w):
            ratio = x / max(1, fill_w - 1)
            color = tuple(int(primary[i] + (primary_end[i] - primary[i]) * ratio) for i in range(3))
            draw.line([(pad + x, y), (pad + x, y + bar_h)], fill=color)
        y += bar_h + 26

        draw.text((pad, y), direction["reason"][:34], font=_font(26), fill=text_dim)
        y += 76

    footer_y = h - 150
    draw.line([(pad, footer_y - 40), (w - pad, footer_y - 40)], fill=(60, 70, 100), width=2)
    draw.text((pad, footer_y), "生意快启 · 30 分钟给你能直接开干的生意启动包", font=_font(30), fill=white)
    draw.text((pad, footer_y + 50), "本图为估算结果，实际以经营情况为准", font=_font(24), fill=text_dim)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- 分享卡片（M2-05）
def _qr_image(content: str, box: int):
    """生成二维码位图。qrcode 为 BSD 许可（白名单内）。"""
    from PIL import Image
    import qrcode

    qr = qrcode.QRCode(border=1, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(content)
    qr.make(fit=True)
    return qr.make_image(fill_color=(15, 23, 42), back_color=(255, 255, 255)).convert("RGB").resize(
        (box, box), Image.NEAREST
    )


def render_share_card(
    city: str,
    tags: dict,
    directions: list[dict],
    share_url: str,
    share_text: str,
) -> bytes:
    """绘制分享卡片（M2-05）：产品名称 + 二维码 + 3 个最热方向。

    PRD 验收：分享卡片包含产品名称与二维码。
    """
    from PIL import Image, ImageDraw

    w, h = 1080, 1350
    top_color = (15, 23, 42)
    bottom_color = (30, 41, 59)
    img = Image.new("RGB", (w, h), top_color)
    draw = ImageDraw.Draw(img)

    for y in range(h):
        ratio = y / max(1, h - 1)
        color = tuple(int(top_color[i] + (bottom_color[i] - top_color[i]) * ratio) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)

    pad = 72
    white = (255, 255, 255)
    text_dim = (170, 180, 210)
    primary = (22, 93, 255)
    primary_end = (123, 97, 255)

    y = pad
    # 产品名（PRD：必须包含产品名称）
    draw.text((pad, y), "生意快启 BizFast", font=_font(52), fill=white)
    y += 74
    draw.text((pad, y), "30 分钟给你能直接开干的生意启动包", font=_font(30), fill=text_dim)
    y += 78
    draw.line([(pad, y), (w - pad, y)], fill=(60, 70, 100), width=2)
    y += 56

    draw.text((pad, y), f"{city} · 我的机会热度图", font=_font(46), fill=white)
    y += 70
    draw.text(
        (pad, y),
        f"{tags.get('capital_label', '')} · {tags.get('time_label', '')}",
        font=_font(30),
        fill=text_dim,
    )
    y += 86

    for idx, direction in enumerate(directions[:3]):
        draw.text((pad, y), f"{idx + 1}. {direction['name']}", font=_font(42), fill=white)
        draw.text((w - pad - 96, y), str(direction["heat"]), font=_font(42), fill=(160, 170, 255))
        y += 60
        bar_w = w - pad * 2
        bar_h = 26
        draw.rounded_rectangle([pad, y, pad + bar_w, y + bar_h], radius=13, fill=(35, 45, 70))
        fill_w = max(36, int(bar_w * direction["heat"] / 100))
        for x in range(fill_w):
            r = x / max(1, fill_w - 1)
            color = tuple(int(primary[i] + (primary_end[i] - primary[i]) * r) for i in range(3))
            draw.line([(pad + x, y), (pad + x, y + bar_h)], fill=color)
        y += bar_h + 22
        draw.text((pad, y), direction["reason"][:30], font=_font(25), fill=text_dim)
        y += 68

    # 二维码区（PRD：必须包含二维码）
    qr_box = 250
    qr_y = h - pad - qr_box
    try:
        qr_img = _qr_image(share_url, qr_box)
        img.paste(qr_img, (w - pad - qr_box, qr_y))
        draw.rectangle(
            [w - pad - qr_box - 8, qr_y - 8, w - pad + 8, qr_y + qr_box + 8],
            outline=(70, 80, 120),
            width=2,
        )
    except Exception:  # pragma: no cover - 二维码失败不影响卡片导出
        logger.warning("分享卡片二维码生成失败，已跳过")

    text_y = qr_y + 6
    draw.text((pad, text_y), "长按识别二维码", font=_font(32), fill=white)
    draw.text((pad, text_y + 48), "看看你的城市适合做什么生意", font=_font(26), fill=text_dim)
    draw.text((pad, text_y + qr_box - 44), share_text[:26], font=_font(24), fill=text_dim)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- 任务创建
async def create_task(db, payload, owner) -> tuple[DiagnosisTask, bool]:
    """创建诊断任务；命中 24h 缓存时直接返回结果（M2-06）。"""
    capital, daily_hours, city = validate_input(payload.capital, payload.daily_hours, payload.city)
    # M2-07 补充问答（可选）：整体跳过或部分作答都不影响主流程
    extra = payload.extra.model_dump() if getattr(payload, "extra", None) else None
    if extra and all(
        extra.get(k) is None for k in ("experience", "mode", "priority")
    ):
        extra = {"skipped": True}

    t0 = time.perf_counter()
    tags = compute_tags(capital, daily_hours, city, extra)
    tag_ms = (time.perf_counter() - t0) * 1000
    if tag_ms > 200:  # pragma: no cover - 兜底告警
        logger.warning("打标耗时超过 200ms：%.1fms", tag_ms)

    cache_key = make_cache_key(capital, daily_hours, city, extra)
    task = DiagnosisTask(
        id=str(uuid.uuid4()),
        user_id=owner.user_id,
        guest_token=owner.guest_token,
        capital=capital,
        daily_hours=daily_hours,
        city=city,
        tags=json.dumps(tags, ensure_ascii=False),
        extra=json.dumps(extra, ensure_ascii=False) if extra else None,
        cache_key=cache_key,
        status="pending",
        stage="queued",
        percent=0,
        message="正在排队诊断",
    )

    cache = get_cache()
    cached_payload = await cache.get_json(f"diag:{cache_key}")
    if cached_payload:
        task.status = "ready"
        task.cached = True
        task.degraded = bool(cached_payload.get("degraded"))
        task.stage = "done"
        task.percent = 100
        task.message = "已为你找到匹配的生意方向"
        task.result = json.dumps(cached_payload, ensure_ascii=False)
        task.heatmap_key = cached_payload.get("heatmap_key")
        task.heatmap_url = (
            get_storage().public_url(task.heatmap_key) if task.heatmap_key else None
        )
        task.finished_at = datetime.now(timezone.utc)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task, True

    db.add(task)
    await db.commit()
    await db.refresh(task)

    run_coroutine(run_diagnose_task(task.id))
    return task, False


# ---------------------------------------------------------------- 后台执行
async def run_diagnose_task(task_id: str) -> None:
    """后台执行诊断：每个阶段做真实计算，进度按真实完成阶段推进（M2-02）。"""
    started = time.perf_counter()
    async with AsyncSessionLocal() as db:
        task = (
            await db.execute(select(DiagnosisTask).where(DiagnosisTask.id == task_id))
        ).scalar_one_or_none()
        if task is None:
            return
        try:
            tags = json.loads(task.tags or "{}")
            state: dict = {"ranked": [], "directions": [], "degraded": False}

            for index, (stage_key, stage_label) in enumerate(STAGES):
                stage_started = time.perf_counter()
                await _do_stage(db, stage_key, state, task, tags)

                done = index + 1
                task.stage = stage_key
                task.percent = int(round(done * 100 / len(STAGES)))
                task.message = stage_label
                task.status = "running"
                await db.commit()

                # UX 节奏参数：保证每阶段至少展示一小段时间，进度条平滑推进（非伪造百分比）
                elapsed_ms = (time.perf_counter() - stage_started) * 1000
                remain = settings.diagnose_stage_min_ms - elapsed_ms
                if remain > 0:
                    await asyncio.sleep(remain / 1000)

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            heatmap_key = state.get("heatmap_key")
            payload = {
                "tags": tags,
                "directions": state["directions"],
                "opportunity_ids": [op["id"] for op, _ in state["ranked"]],
                "scores": {op["id"]: score for op, score in state["ranked"]},
                "case_count": opp_data.CASE_COUNT,
                "elapsed_ms": elapsed_ms,
                "degraded": bool(state["degraded"]),
                "heatmap_key": heatmap_key,
            }

            task.result = json.dumps(payload, ensure_ascii=False)
            task.heatmap_key = heatmap_key
            task.heatmap_url = get_storage().public_url(heatmap_key) if heatmap_key else None
            task.status = "ready"
            task.percent = 100
            task.message = "已为你找到匹配的生意方向"
            task.degraded = bool(state["degraded"])
            task.finished_at = datetime.now(timezone.utc)
            await db.commit()

            cache = get_cache()
            await cache.set_json(
                f"diag:{task.cache_key}", payload, ttl=settings.diagnose_cache_ttl_seconds
            )
        except Exception as exc:  # pragma: no cover - 兜底
            logger.exception("诊断任务失败：%s", exc)
            task.status = "failed"
            task.message = "诊断失败，请点击重试"
            await db.commit()


async def _do_stage(db, stage_key: str, state: dict, task: DiagnosisTask, tags: dict) -> None:
    """单个阶段的真实计算。"""
    if stage_key == "scan":
        state["tier_weights"] = city_data.TIER_WEIGHTS[tags["city_level"]]
        prompt = (
            f"用户在{task.city}，启动资金{task.capital}元，每天可投入{task.daily_hours}小时。"
            f"请用一句不超过 30 字的中文给出最值得尝试的方向。"
        )
        owner_key = (
            f"guest:{task.guest_token}" if task.guest_token else f"user:{task.user_id}"
        )
        # V5.0 闸门 6：预算熔断 —— 触及上限时自动降级模板/规则引擎，不拒绝服务
        budget = await ai_cost.check_budget(db, owner_key, "none", "diagnose")
        # V5.0 闸门 4：轮数上限（诊断 ≤8 轮）——超限同样降级模板模式，不放出超长智能体任务
        rounds_gate = ai_cost.check_rounds("diagnose", 1)
        if budget["allow_ai"] and rounds_gate["allow_ai"]:
            text, degraded = ai_client.try_complete(prompt)
        else:
            text, degraded = None, True
            state["template_mode"] = True
        state["degraded"] = degraded
        # V5.0 第 7 章：AI 成本记账（诊断 ≤8 轮上限；本阶段为 1 轮）
        await ai_cost.record_ai_call(
            db,
            "diagnose",
            prompt,
            text,
            owner_key=owner_key,
            cache_hit=False,
            template_mode=bool(state.get("template_mode")),
            rounds=int(rounds_gate["capped_rounds"]),
        )
        await db.flush()

    elif stage_key == "match":
        state["ranked"] = rank_opportunities(tags, task.capital, task_extra(task))

    elif stage_key == "payback":
        state["payback"] = [
            {"id": op["id"], "payback_months": op["payback_months"], "margin_pct": op["margin_pct"]}
            for op, _ in state["ranked"][:8]
        ]

    elif stage_key == "cases":
        state["case_count"] = opp_data.CASE_COUNT
        state["cases_ok"] = all(len(op["cases"]) >= 2 for op, _ in state["ranked"][:4])

    elif stage_key == "heatmap":
        directions = build_directions(tags, state["ranked"])
        state["directions"] = directions
        png = render_heatmap(task.city, tags, directions, opp_data.CASE_COUNT)
        key = f"heatmaps/{task.city}_{task.cache_key}.png"
        get_storage().save_bytes(key, png)
        state["heatmap_key"] = key


# ---------------------------------------------------------------- 查询
def _done_count(task: DiagnosisTask) -> int:
    keys = [key for key, _ in STAGES]
    if task.status == "ready":
        return len(keys)
    if task.stage in keys:
        return keys.index(task.stage) + 1
    return 0


def get_progress(task: DiagnosisTask) -> dict:
    done = _done_count(task)
    return {
        "task_id": task.id,
        "status": task.status,
        "stage": task.stage,
        "percent": task.percent,
        "message": task.message,
        "stages": STAGE_LABELS,
        "done_stages": STAGE_LABELS[:done],
    }


def result_payload(task: DiagnosisTask) -> dict:
    result = json.loads(task.result or "{}")
    return {
        "task_id": task.id,
        "status": task.status,
        "city": task.city,
        "tags": json.loads(task.tags or "{}"),
        "directions": result.get("directions", []),
        "heatmap_url": task.heatmap_url or "",
        "cached": task.cached,
        "degraded": task.degraded,
        "case_count": result.get("case_count", opp_data.CASE_COUNT),
        "elapsed_ms": result.get("elapsed_ms", 0),
        # M2-07：回显补充问答；跳过则为 None（前端据此显示「已跳过」）
        "extra": task_extra(task) or None,
    }


def task_extra(task: DiagnosisTask) -> dict | None:
    if not task.extra:
        return None
    try:
        return json.loads(task.extra)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 分享卡片（M2-05）
def share_card_payload(task: DiagnosisTask, share_url: str) -> dict:
    """M2-05：分享卡片数据（产品名 + 二维码 + 3 个最热方向）+ 文案。"""
    result = json.loads(task.result or "{}")
    tags = json.loads(task.tags or "{}")
    directions = result.get("directions", [])[:3]
    names = "、".join(d["name"] for d in directions) if directions else "机会方向"
    share_text = f"我在{city_label(task.city)}测出来最适合做：{names}，你也来测测？"
    return {
        "task_id": task.id,
        "image_url": f"/api/diagnose/share-card/{task.id}",
        "title": f"{city_label(task.city)} 机会热度图",
        "subtitle": f"{tags.get('capital_label', '')} · {tags.get('time_label', '')}",
        "directions": directions,
        "qr_content": share_url,
        "share_text": share_text,
        "share_url": share_url,
    }


def city_label(city: str) -> str:
    return city or "你所在城市"


def render_share_card_for_task(task: DiagnosisTask, share_url: str) -> bytes:
    result = json.loads(task.result or "{}")
    tags = json.loads(task.tags or "{}")
    directions = result.get("directions", [])[:3]
    names = "、".join(d["name"] for d in directions) if directions else "机会方向"
    text = f"我在{city_label(task.city)}测出来最适合做：{names}"
    return render_share_card(task.city, tags, directions, share_url, text)


async def get_task(db, task_id: str) -> DiagnosisTask:
    task = (
        await db.execute(select(DiagnosisTask).where(DiagnosisTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise BizError(40401, "未找到对应的诊断任务，请重新诊断")
    return task
