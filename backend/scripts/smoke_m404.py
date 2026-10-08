"""V5.0 M4-04 端到端验证：后台商机 / 提示词调整 → 用户端确实生效。

修复前的事实是：后台商机库读写的是一份独立的演示数据（OP-2001…OP-2005），
提示词配置也从没被用户端读过 —— 运营改了「看得见、不生效」。

本脚本用真实 HTTP 调用证明修复后链路贯通：
    后台改标题/资金区间 → 用户端商机详情立刻是新值
    后台下架          → 用户端立刻 40401
    后台回滚          → 用户端回到历史版本
    后台改提示词      → 「测试」返回的就是新提示词
    改一条商机        → 其余 18 条基线商机仍在（商机库不塌缩）

前置：后端已在 127.0.0.1:8077 运行。
运行：cd backend && .venv/Scripts/python.exe scripts/smoke_m404.py
"""
from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8077"
TARGET = "op_breakfast_cart"          # 社区便民早餐车（代码基线商机）
NEW_TITLE = "【运营改名】社区便民早餐车"
DEFAULT_DIAGNOSE = (
    "用户在{city}，启动资金{capital}元，每天可投入{daily_hours}小时。"
    "请用一句不超过 30 字的中文给出最值得尝试的方向。"
)

passed: list[str] = []
failed: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    (passed if cond else failed).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f"   <- {extra}" if extra else ""))


def unwrap(resp: httpx.Response):
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {body}")
    return body["data"]


def cmin(d: dict):
    """用户端商机卡片把资金放在 metrics 里（snake→camel 出口后为 capitalMinYuan）。"""
    m = d.get("metrics") or {}
    return m.get("capitalMinYuan", m.get("capital_min_yuan"))


def payback_text(d: dict):
    return (d.get("five_elements") or d.get("fiveElements") or {}).get("payback")


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30.0)

    # ── 后台登录（账号密码 + TOTP）──
    unwrap(c.post("/api/admin/auth/login", json={"username": "admin", "password": "admin123"}))
    token = unwrap(
        c.post("/api/admin/auth/verify-2fa", json={"username": "admin", "totp": "123456"})
    )["token"]
    h = {"Authorization": f"Bearer {token}"}
    print("== 后台登录完成 ==\n")

    # ── 1. 后台列表 = 用户端真实商机库 ──
    print("1) 后台商机库数据源")
    data = unwrap(c.get("/api/admin/opportunities", params={"pageSize": 100}, headers=h))
    ids = [o["id"] for o in data["items"]]
    check("后台列表 = 用户端真实商机库（>=19 条）", data["total"] >= 19, f"total={data['total']}")
    check("不再出现 OP-2001 等演示假数据", not any(str(i).startswith("OP-") for i in ids), f"ids[0]={ids[0]}")
    check("目标基线商机在后台可见", TARGET in ids)

    # ── 2. 用户端基线读数 ──
    print("\n2) 用户端基线")
    d0 = unwrap(c.get(f"/api/match/{TARGET}"))
    print("   用户端详情字段:", list(d0.keys()))
    t0, c0 = d0.get("title"), cmin(d0)
    check("用户端可读到该商机", bool(t0), f"title={t0} capitalMinYuan={c0} 回本={payback_text(d0)}")
    # 记录基线整行，供结束前还原（避免验证残留污染运营配置）
    base_row = next((o for o in data["items"] if o["id"] == TARGET), {})

    try:
        # ── 3. 后台改标题 + 资金区间 → 用户端应立即生效 ──
        print("\n3) 后台编辑 → 用户端生效（V5.0 M4-04 核心）")
        saved = unwrap(c.put(
            f"/api/admin/opportunities/{TARGET}",
            headers=h,
            json={
                "title": NEW_TITLE,
                "category": "餐饮小吃",
                "capitalMin": 18000,
                "capitalMax": 45000,
                "paybackMonths": 4,
                "marginPercent": 55,
                "difficultyStars": 2,
            },
        ))
        check("后台保存成功", saved.get("title") == NEW_TITLE, f"title={saved.get('title')}")

        data2 = unwrap(c.get("/api/admin/opportunities", params={"pageSize": 100}, headers=h))
        hit = next((o for o in data2["items"] if o["id"] == TARGET), None)
        check("后台列表显示新标题", bool(hit) and hit["title"] == NEW_TITLE)
        print("   后台该行:", json.dumps(
            {k: v for k, v in (hit or {}).items()
             if k in ("id", "title", "capitalMin", "capital_max", "capitalMax",
                      "paybackMonths", "marginPercent", "difficultyStars", "onShelf")},
            ensure_ascii=False,
        ))
        check("后台列表显示新资金区间（snake/camel 契约漂移已修）",
              bool(hit) and hit.get("capitalMin") == 18000,
              f"capitalMin={hit and hit.get('capitalMin')}")

        d1 = unwrap(c.get(f"/api/match/{TARGET}"))
        check("【核心】用户端标题已即时更新", d1.get("title") == NEW_TITLE, f"title={d1.get('title')}")
        check("【核心】用户端资金区间已即时更新", cmin(d1) == 18000, f"capitalMinYuan={cmin(d1)}")
        check("【核心】用户端回本周期已即时更新", payback_text(d1) == "4个月",
              f"回本={payback_text(d1)}")

        # 关键回归点：有 overlay 时商机库必须是「基线 + 调整」，
        # 而不是只剩运营动过的那几条（否则匹配列表凑不够 4 张卡片 → 50001）
        other = next((i for i in ids if i != TARGET), None)
        do = unwrap(c.get(f"/api/match/{other}"))
        check("改一条商机后其他基线商机仍在（商机库未塌缩）",
              bool(do.get("title")), f"{other} -> {do.get('title')}")

        # ── 4. 下架 → 用户端不可见（走前端真实使用的 camelCase 请求体）──
        print("\n4) 后台下架 → 用户端不可见")
        unwrap(c.put(f"/api/admin/opportunities/{TARGET}/shelf", headers=h, json={"onShelf": False}))
        body = c.get(f"/api/match/{TARGET}").json()
        check("下架后用户端读不到（40401）", body.get("code") == 40401, f"code={body.get('code')}")

        # ── 5. 重新上架 ──
        unwrap(c.put(f"/api/admin/opportunities/{TARGET}/shelf", headers=h, json={"onShelf": True}))
        d2 = unwrap(c.get(f"/api/match/{TARGET}"))
        check("重新上架后用户端恢复，且仍是运营改后的值", d2.get("title") == NEW_TITLE)

        # ── 6. 版本回滚 ──
        print("\n5) 后台版本回滚 → 用户端回到旧值")
        vers = unwrap(c.get(f"/api/admin/opportunities/{TARGET}/versions", headers=h))
        vlist = vers.get("versions", [])
        check("版本历史已自动记录", len(vlist) >= 1, f"n={len(vlist)}")
        if vlist:
            v1 = vlist[0]["version"]
            unwrap(c.post(f"/api/admin/opportunities/{TARGET}/rollback", headers=h, json={"version": v1}))
            d3 = unwrap(c.get(f"/api/match/{TARGET}"))
            check("回滚后用户端标题恢复原值", d3.get("title") == t0, f"title={d3.get('title')}")

        # ── 7. 提示词配置真正生效 ──
        print("\n6) 后台提示词配置 → 用户端调用确认")
        marker = "【验证】{city} 启动资金 {capital} 元，每天 {daily_hours} 小时，给一句方向。"
        unwrap(c.put("/api/admin/prompts/diagnose", headers=h, json={"content": marker, "model": "gpt-4"}))
        t = unwrap(c.post("/api/admin/prompts/diagnose/test", headers=h))
        echoed = t.get("prompt") or ""
        check("「测试」回显的就是刚保存的提示词（运营所见即所得）",
              "【验证】" in echoed, f"prompt={echoed[:80]}")
        check("占位符被真实参数填充", "上海" in echoed and "50000" in echoed, f"prompt={echoed[:80]}")

    finally:
        # ── 清理：按基线整行还原，避免验证残留影响后续 ──
        print("\n7) 清理还原")
        try:
            c.put(f"/api/admin/opportunities/{TARGET}/shelf", headers=h, json={"onShelf": True})
            c.put(
                f"/api/admin/opportunities/{TARGET}",
                headers=h,
                json={
                    "title": base_row.get("title", t0),
                    "category": base_row.get("category", "未分类"),
                    "capitalMin": base_row.get("capitalMin", 0),
                    "capitalMax": base_row.get("capitalMax", 0),
                    "paybackMonths": base_row.get("paybackMonths", 0),
                    "marginPercent": base_row.get("marginPercent", 0),
                    "difficultyStars": base_row.get("difficultyStars", 1),
                },
            )
            c.put("/api/admin/prompts/diagnose", headers=h, json={"content": DEFAULT_DIAGNOSE})
            d9 = unwrap(c.get(f"/api/match/{TARGET}"))
            check("还原后用户端标题回到基线", d9.get("title") == t0, f"title={d9.get('title')}")
            print("   已还原商机与提示词")
        except Exception as exc:  # pragma: no cover
            print("   还原失败：", exc)

    print(f"\n===== 结果：{len(passed)} 通过 / {len(failed)} 失败 =====")
    for name in failed:
        print("  FAIL:", name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
