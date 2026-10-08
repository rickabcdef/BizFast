"""V5.0 M3-06 / M5-02 开业喜报生成（P0）。

- 下载完成后提供「生成开业喜报」入口，生成一张可发朋友圈的喜报图（10 秒内）；
- 喜报模板 ≥ 3 种可选；分享出去不显突兀；
- 合规：喜报不带硬付费引导，只带品牌标识与 slogan。

实现：Pillow 纯代码绘制（零版权风险、零模型成本），落库支撑「我的喜报与素材」。
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.context import ensure_owner_user, owner_key_for_user
from app.core.errors import BizError
from app.models import Order, ShareReport
from app.services import ai_cost
from app.storage import get_storage

logger = logging.getLogger(__name__)

BRAND = "生意快启"
SLOGAN = "30 分钟，给你能直接开干的生意启动包"
WIDTH, HEIGHT = 1080, 1440

# 三种模板（配色不同、布局一致，保证「分享出去不显突兀」）
REPORT_TEMPLATES: dict[int, dict] = {
    1: {
        "name": "科技蓝紫",
        "bg": (15, 23, 42),
        "bg2": (30, 41, 59),
        "accent": (22, 93, 255),
        "accent2": (123, 97, 255),
        "title": (255, 255, 255),
        "desc": (170, 180, 210),
    },
    2: {
        "name": "开业红金",
        "bg": (60, 16, 24),
        "bg2": (96, 28, 36),
        "accent": (245, 63, 63),
        "accent2": (255, 178, 60),
        "title": (255, 245, 235),
        "desc": (235, 200, 200),
    },
    3: {
        "name": "简约白蓝",
        "bg": (245, 248, 255),
        "bg2": (226, 236, 255),
        "accent": (22, 93, 255),
        "accent2": (0, 150, 136),
        "title": (18, 32, 60),
        "desc": (90, 108, 140),
    },
}

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
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


def _lerp(c1, c2, t: float):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def render_report(
    template: int, title: str, subtitle: str, lines: list[str], footer: str = SLOGAN
) -> bytes:
    """用 Pillow 绘制喜报图（1080×1440 竖版，适配朋友圈）。"""
    from PIL import Image, ImageDraw

    cfg = REPORT_TEMPLATES.get(template, REPORT_TEMPLATES[1])
    img = Image.new("RGB", (WIDTH, HEIGHT), cfg["bg"])
    draw = ImageDraw.Draw(img)

    # 渐变背景
    for y in range(HEIGHT):
        draw.line([(0, y), (WIDTH, y)], fill=_lerp(cfg["bg"], cfg["bg2"], y / HEIGHT))

    # 顶部品牌条
    draw.rectangle([0, 0, WIDTH, 12], fill=cfg["accent"])
    draw.text((72, 92), BRAND, font=_font(40), fill=cfg["accent"])
    draw.text((WIDTH - 72 - 168, 96), "开 业 喜 报", font=_font(34), fill=cfg["desc"])

    # 主标题
    y = 320
    draw.text((72, y), "🎉", font=_font(84), fill=cfg["accent2"])
    y += 130
    draw.text((72, y), title, font=_font(66), fill=cfg["title"])
    y += 110
    draw.text((72, y), subtitle, font=_font(34), fill=cfg["desc"])
    y += 100

    # 分隔渐变线
    for x in range(72, WIDTH - 72):
        draw.point((x, y), fill=_lerp(cfg["accent"], cfg["accent2"], (x - 72) / (WIDTH - 144)))
    y += 60

    # 要点清单
    for i, line in enumerate(lines[:6]):
        draw.ellipse([76, y + 14, 96, y + 34], fill=cfg["accent"])
        draw.text((120, y), line, font=_font(38), fill=cfg["title"])
        y += 78

    # 底部 slogan + 日期
    draw.text((72, HEIGHT - 190), footer, font=_font(32), fill=cfg["desc"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    draw.text((72, HEIGHT - 132), f"{BRAND} · {today}", font=_font(28), fill=cfg["desc"])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _order_context(db, order: Order) -> dict:
    """从订单反查诊断信息，构造喜报文案字段。"""
    from app.data import opp_library
    from app.models import DiagnosisTask

    diag = (
        await db.execute(
            select(DiagnosisTask)
            .where(DiagnosisTask.user_id == order.user_id)
            .order_by(DiagnosisTask.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    pool = opp_library.library()
    opp = pool[0] if pool else {}
    if order.match_id:
        for o in pool:
            if o.get("id") == order.match_id:
                opp = o
                break
    return {
        "city": diag.city if diag else "上海",
        "capital": diag.capital if diag else 50000,
        "opp_title": opp.get("title", "我的小生意"),
        "payback": opp.get("payback_months"),
        "margin": opp.get("margin_pct"),
    }


def build_content(ctx: dict) -> tuple[str, str, list[str]]:
    """喜报文案（模板化，不带付费引导）。"""
    title = f"我的「{ctx['opp_title']}」开干啦"
    subtitle = f"坐标 {ctx['city']}｜10 件开干交付物已就位"
    lines = [
        "商机方向、回本测算、定价方案全部算清楚了",
        "获客文案、开业海报、收款码一次备齐",
        "30 天逐日行动日历，每天照着做就行",
        "风险清单与止损线，心里有底不慌",
    ]
    if ctx.get("payback"):
        lines.insert(1, f"预计 {ctx['payback']} 个月回本，毛利率约 {ctx.get('margin', 0)}%")
    return title, subtitle, lines


async def create_report(db, owner, order_id: str | None, template: int = 1) -> dict:
    """M3-06：生成开业喜报（10 秒内）。落库 + 存对象存储，返回可分享的图片地址。"""
    if template not in REPORT_TEMPLATES:
        template = 1
    user = await ensure_owner_user(db, owner)

    order = None
    if order_id:
        order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
        if order is not None and order.user_id != user.id:
            raise BizError(40301, "无权访问该订单")

    ctx = await _order_context(db, order) if order else {
        "city": "上海", "capital": 50000, "opp_title": "我的小生意", "payback": 3, "margin": 40,
    }
    title, subtitle, lines = build_content(ctx)
    png = render_report(template, title, subtitle, lines)

    key = f"reports/{user.id}/{uuid.uuid4().hex}.png"
    url = get_storage().save_bytes(key, png)

    report = ShareReport(
        id=str(uuid.uuid4()),
        user_id=user.id,
        order_id=order_id,
        template=template,
        title=title,
        subtitle=subtitle,
        image_url=url,
        data=json.dumps({"lines": lines, "city": ctx["city"]}, ensure_ascii=False),
    )
    db.add(report)
    # 模板化成本记账（喜报为纯模板绘制，成本可忽略）
    await ai_cost.record_call(
        db, "report", prompt_tokens=100, completion_tokens=120,
        owner_key=owner_key_for_user(user), template_mode=True, model="template-engine",
    )
    await db.commit()
    await db.refresh(report)
    logger.info("开业喜报已生成：user=%s template=%s", user.id, template)
    return payload(report)


def payload(report: ShareReport) -> dict:
    try:
        data = json.loads(report.data or "{}")
    except json.JSONDecodeError:
        data = {}
    return {
        "id": report.id,
        "order_id": report.order_id,
        "template": report.template,
        "template_name": REPORT_TEMPLATES.get(report.template, {}).get("name", ""),
        "title": report.title,
        "subtitle": report.subtitle,
        "image_url": report.image_url,
        "lines": data.get("lines", []),
        "brand": BRAND,
        "slogan": SLOGAN,
        "no_paywall": True,
    }


async def list_templates() -> list[dict]:
    return [{"id": k, "name": v["name"]} for k, v in REPORT_TEMPLATES.items()]


async def list_reports(db, owner) -> list[dict]:
    """M10：我的喜报与素材。"""
    user = await ensure_owner_user(db, owner)
    rows = (
        await db.execute(
            select(ShareReport)
            .where(ShareReport.user_id == user.id)
            .order_by(ShareReport.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return [payload(r) for r in rows]
