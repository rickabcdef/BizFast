"""商机库「有效视图」：代码基线 + 后台运营调整（V5.0 M4-04）。

背景（真实存在的缺陷）
--------------------
后台「商机库管理」把运营的编辑结果写进 ``backend/data/admin_config/opportunities.json``，
但用户端的诊断 / 匹配 / 启动包 / 谈资卡 / 喜报全都直接读代码常量
``app.data.opportunities.OPPORTUNITIES``。两边各说各话，结果是：

    运营在后台改了商机标题、把某个商机下架、审核通过一个新增商机
    → 用户端**毫无变化**，后台那句「修改后 5 分钟内对用户端生效，无需发版」
      从来没有兑现过（典型的「看得见、不生效」）。

本模块把后台运营调整叠加到代码基线上，作为**用户端商机数据的唯一入口**：

- 编辑（标题 / 品类 / 资金区间 / 回本周期 / 毛利率 / 难度）→ 用户端即时看到新数字；
- 驳回、下架、删除 → 用户端不再推荐该商机；
- 后台新增且「已通过 + 已上架」→ 用户端可见；内容不全会用**诚信占位**
  （明确写「运营新增，暂无第三方公开案例」），绝不编造案例与来源。

安全兜底：后台从未配置过（文件不存在）时，返回结果与改动前**完全一致**，
只读代码基线，不影响任何既有链路。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.data.opportunities import OPPORTUNITIES, OPPORTUNITY_INDEX

logger = logging.getLogger(__name__)

# 与 app/services/admin.py 的 CONFIG_DIR 指向同一处（backend/data/admin_config）
_OVERLAY_PATH = Path(__file__).resolve().parents[2] / "data" / "admin_config" / "opportunities.json"

# 后台字段 → 用户端商机字段
_FIELD_MAP = {
    "title": "title",
    "category": "category",
    "capitalMin": "capital_min",
    "capitalMax": "capital_max",
    "paybackMonths": "payback_months",
    "marginPercent": "margin_pct",
    "difficultyStars": "difficulty",
    "summary": "summary",
    "icon": "icon",
}

# 兼容层：后台 `_dump(body)` 默认输出 snake_case（model_dump 不按别名），
# 而前端与后台列表用的是 camelCase。若不做归一化，运营改资金区间 / 回本 / 毛利
# 会写进一个谁都不读的 `capital_min` 键，界面显示旧值、用户端也拿不到新值。
_SNAKE_TO_CAMEL = {
    "capital_min": "capitalMin",
    "capital_max": "capitalMax",
    "payback_months": "paybackMonths",
    "margin_percent": "marginPercent",
    "difficulty_stars": "difficultyStars",
    "status_label": "statusLabel",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "deleted_at": "deletedAt",
}


def _normalize(rec: dict) -> dict:
    """把运营记录里的 snake_case 键统一成 camelCase（同名键优先保留 camelCase）。"""
    out: dict = {}
    for key, value in rec.items():
        camel = _SNAKE_TO_CAMEL.get(key)
        if camel is None:
            out[key] = value
        elif camel not in rec:  # 两种形式都存在时以 camelCase 为准
            out[camel] = value
    return out

_CATEGORY_ICON = {
    "社区零售": "🛒",
    "餐饮小吃": "🍜",
    "本地生活服务": "🧰",
    "宠物服务": "🐾",
    "教育培训": "📚",
    "新媒体服务": "📹",
    "汽车服务": "🚗",
    "空间服务": "🏠",
    "二手回收": "♻️",
}

_STATUS_LABEL = {"passed": "已通过", "pending": "待审核", "rejected": "已驳回", "deleted": "已删除"}

# 缓存：(文件 mtime, 有效商机列表)
_cache: dict[str, object] = {"mtime": None, "items": None}


def _load_overlay() -> list[dict] | None:
    """读后台配置；文件不存在时返回 None（表示「运营还没配置过」）。"""
    if not _OVERLAY_PATH.exists():
        return None
    try:
        data = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - 配置损坏不应影响用户端
        logger.warning("后台商机配置解析失败，回退代码基线：%s", exc)
        return None
    if not isinstance(data, list):
        return None
    return [_normalize(rec) for rec in data if isinstance(rec, dict)]


def _apply_fields(base: dict, rec: dict) -> dict:
    """把后台记录里能映射的字段覆盖到用户端商机字典上（不改原对象）。"""
    merged = dict(base)
    for admin_key, opp_key in _FIELD_MAP.items():
        if admin_key in rec and rec[admin_key] not in (None, ""):
            merged[opp_key] = rec[admin_key]
    return merged


def _publishable(rec: dict) -> bool:
    """只有「已通过」且「已上架」的商机才对用户端可见（M4-04）。"""
    return rec.get("status") == "passed" and bool(rec.get("onShelf"))


def _synthesize(rec: dict) -> dict | None:
    """后台新增的商机 → 用户端卡片。

    运营在后台只填了标题/品类/城市/资金/回本/毛利/难度，缺少案例、风险等长文案。
    这里用**诚实占位**补齐：风险与步骤是通用经营提示（不是编造数据），
    案例明确标注「运营新增，暂无第三方公开案例」，避免假案例流入用户端。
    """
    title = (rec.get("title") or "").strip()
    if not title:
        return None
    category = rec.get("category") or "社区零售"
    cap_min = int(rec.get("capitalMin") or 0)
    cap_max = int(rec.get("capitalMax") or max(cap_min, 0))
    payback = int(rec.get("paybackMonths") or 6)
    margin = int(rec.get("marginPercent") or 40)
    difficulty = int(rec.get("difficultyStars") or 3)
    created = (rec.get("createdAt") or "")[:10] or "近期"
    owned = (rec.get("source") or "运营录入")

    return {
        "id": rec.get("id"),
        "title": title,
        "icon": rec.get("icon") or _CATEGORY_ICON.get(category, "💡"),
        "category": category,
        "capital_min": cap_min,
        "capital_max": cap_max,
        "time_requirement": rec.get("timeRequirement") or "part",
        "city_tiers": ["tier1", "new_tier1", "tier2", "tier3", "tier4"],
        "payback_months": payback,
        "margin_pct": margin,
        "difficulty": difficulty,
        "first_customer": rec.get("firstCustomer") or f"{title}的社区群、周边商户与老顾客，是第一批客户",
        "summary": rec.get("summary") or f"{title}：{category}方向的轻资产选择，启动资金约 {cap_min}–{cap_max} 元，预计 {payback} 个月左右回本。",
        "tags": ["运营新增", category, "轻资产"],
        "risks": [
            f"最容易亏在：一开始就按最大规模投入，{title}的现金流还没跑起来资金就先紧了",
            "同类生意在周边已经有人做，不打差异就只能拼价格，利润会被压薄",
            "客流与复购全靠选点与口碑，位置或服务掉链子，回本周期会被拉长一倍",
        ],
        "stop_loss": f"连续 30 天日均营收低于当月固定支出的 60%，或累计亏损超过启动资金的 30%，立即收缩规模止损",
        "cases": [
            {
                "title": f"{title}（运营新增商机）",
                "source": f"生意快启运营录入 · {owned}",
                "time": created,
                "highlight": "该商机由运营在后台新增，暂无第三方公开案例，请结合本地实地调研判断",
            },
            {
                "title": f"{title}（待补充公开案例）",
                "source": "生意快启运营录入",
                "time": created,
                "highlight": "建议先用最小规模试跑 2–4 周，用真实数据验证再决定是否放量",
            },
        ],
        "cost_breakdown": [
            {"item": "首批备货 / 物料", "amount": f"{int(cap_min * 0.5)}–{int(cap_max * 0.6)} 元", "note": "先小批量试，别一次性铺满"},
            {"item": "场地 / 摊位 / 设备", "amount": f"{int(cap_min * 0.3)}–{int(cap_max * 0.3)} 元", "note": "能租不买，先验证客流"},
            {"item": "开业推广与杂项", "amount": f"{int(max(cap_min * 0.1, 200))}–{int(max(cap_max * 0.1, 500))} 元", "note": "优先做邻里与社群，别烧广告"},
        ],
        "revenue_estimate": [
            {"item": "客单价", "value": f"参考 {category} 常见区间", "note": "按本地实际定价调整"},
            {"item": "毛利率", "value": f"{margin}%", "note": "估算值，实际以经营情况为准"},
            {"item": "回本周期", "value": f"约 {payback} 个月", "note": "估算值，实际以经营情况为准"},
        ],
        "target_customers": rec.get("targetCustomers") or f"{title}周边 3 公里内的常住居民与上班族",
        "channels": rec.get("channels") or "小区社群、周边商户合作、本地生活平台、老客转介绍",
        "skill_required": rec.get("skillRequired") or "不需要专门技术，肯花时间、会算账、能坚持更重要",
        "steps": [
            "第 1 步：用最小规模试跑，先做 20 个种子客户，验证有没有人愿意付钱",
            "第 2 步：算出真实单客毛利与日均订单，确认能覆盖固定支出",
            "第 3 步：把跑通的流程写成固定动作，招兼职或家人帮忙复制",
            "第 4 步：稳定 2 个月后再考虑加品、加点位或加人",
        ],
        "intro": rec.get("intro") or f"{title}是运营在后台新增的商机方向，请结合你所在城市的实际情况判断可行性。",
    }


def _build() -> list[dict]:
    overlay = _load_overlay()
    if overlay is None:
        # 运营还没配置过：完全按代码基线走（与改动前行为一致）
        return list(OPPORTUNITIES)

    items: list[dict] = []
    seen: set[str] = set()

    # 1) 运营记录优先（改过的排在前面）
    for rec in overlay:
        opp_id = rec.get("id")
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)  # 先占位：被驳回 / 下架 / 删除的商机也不能被基线补回来
        base = OPPORTUNITY_INDEX.get(opp_id)
        if base is not None:
            # 基线商机：应用字段覆盖；被驳回 / 下架 / 删除 → 用户端不出现
            if _publishable(rec):
                items.append(_apply_fields(base, rec))
        else:
            # 后台新增商机：审核通过且上架才发布
            if _publishable(rec):
                synthesized = _synthesize(rec)
                if synthesized is not None:
                    items.append(synthesized)

    # 2) 基线里运营尚未触碰的商机原样保留。
    #    少了这一步，只要后台动过任意一条商机，整个商机库就会塌缩成
    #    overlay 里的那几条（匹配列表凑不够 4 张卡片，直接 50001）。
    for op in OPPORTUNITIES:
        if op["id"] in seen:
            continue
        items.append(op)
    return items


def library() -> list[dict]:
    """用户端商机库（含后台运营调整）。按文件 mtime 做进程内缓存。"""
    try:
        mtime = _OVERLAY_PATH.stat().st_mtime if _OVERLAY_PATH.exists() else None
    except OSError:  # pragma: no cover
        mtime = None
    if _cache["items"] is None or _cache["mtime"] != mtime:
        _cache["items"] = _build()
        _cache["mtime"] = mtime
    return list(_cache["items"])  # type: ignore[arg-type]


def index() -> dict[str, dict]:
    return {op["id"]: op for op in library()}


# ---------------------------------------------------------------- 后台管理视图（M4-04）

def _admin_record(base: dict, rec: dict | None) -> dict:
    """用户端商机（+ 运营记录）→ 后台管理记录。

    后台当初用的是另一套字段名（capitalMin/paybackMonths/difficultyStars…），
    这里做一次映射，让「后台看到的商机」与「用户端在用的商机」是同一份数据。
    """
    item = {
        "id": base.get("id"),
        "title": base.get("title", ""),
        "category": base.get("category", ""),
        "icon": base.get("icon", ""),
        "summary": base.get("summary", ""),
        "capitalMin": base.get("capital_min", 0),
        "capitalMax": base.get("capital_max", 0),
        "paybackMonths": base.get("payback_months", 0),
        "marginPercent": base.get("margin_pct", 0),
        "difficultyStars": base.get("difficulty", 3),
        # 基线商机默认就是「已通过 + 已上架」，运营改动时才被 rec 覆盖
        "city": "全国",
        "source": "案例库",
        "status": "passed",
        "onShelf": True,
        # 代码内置商机没有「创建 / 修改时间」，用「内置」标注而不是编一个时间
        "createdAt": "内置",
        "updatedAt": "内置",
    }
    for key, value in (rec or {}).items():
        if value is not None:
            item[key] = value
    item["statusLabel"] = _STATUS_LABEL.get(item.get("status"), item.get("statusLabel") or "待审核")
    return item


def admin_list() -> list[dict]:
    """后台商机库列表：用户端真实商机库 + 运营调整（含未上架 / 待审核的）。

    与 ``library()`` 的区别：``library()`` 只返回用户端**可见**的商机，
    而运营必须看得到自己驳回 / 下架的，所以这里不做可见性过滤。
    """
    overlay = _load_overlay() or []
    items: list[dict] = []
    seen: set[str] = set()

    # 先放运营记录（新增商机在内，符合后台「最新在前」的习惯）
    for rec in overlay:
        if not isinstance(rec, dict):
            continue
        opp_id = rec.get("id")
        if not opp_id or opp_id in seen:
            continue
        seen.add(opp_id)
        if rec.get("status") == "deleted":
            continue  # 墓碑记录：后台列表不展示，同时阻止基线把它补回来
        items.append(_admin_record(OPPORTUNITY_INDEX.get(opp_id) or {}, rec))

    # 再补齐代码基线里运营尚未触碰的商机（被墓碑删除的除外，已进 seen）
    for op in OPPORTUNITIES:
        if op["id"] in seen:
            continue
        items.append(_admin_record(op, None))
    return items


def get(opportunity_id: str) -> dict | None:
    return index().get(opportunity_id)


def refresh() -> None:
    """后台保存后调用，让下一次读取立刻重建（无需等 mtime 变化）。"""
    _cache["items"] = None
    _cache["mtime"] = None
