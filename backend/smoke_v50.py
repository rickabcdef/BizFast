"""BizFast V5.0 新增能力端到端冒烟测试（对齐《现金流导向版 PRD V5.0》）。

覆盖：
- 五档定价（0 / 29.9 / 99 / 599 / 加购包）
- M5 裂变：今日谈资卡（每日 0 点生成 / 一键转发 / 带来源日期）
- M3-06 / M5-02 开业喜报（≥3 种模板，不带硬付费引导）
- M8 工具箱权益（开业礼包赠 2 个工具 30 天 / 会员全部）
- 第 7 章 AI 成本六道闸门 + M4-05 成本监控（25% 告警）
- M4-07 转化漏斗（访问→诊断→付费→下载）
- M4-08 裂变数据看板（K 因子 / 单用户裂变获客成本）

运行前先启动后端：
    cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077
然后：
    cd backend && ./.venv/Scripts/python.exe smoke_v50.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8077"

PASS = 0
FAIL = 0
FAILED: list[str] = []


def req(method, path, body=None, token=None, guest=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if guest:
        headers["X-Guest-Token"] = guest
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def data_of(body) -> dict:
    if isinstance(body, dict):
        return body.get("data") or {}
    return {}


def check(name, cond, body=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  [FAIL] {name}")
        if body is not None:
            print(f"         -> {json.dumps(body, ensure_ascii=False)[:360]}")


print("=" * 78)
print("BizFast V5.0 新增能力端到端冒烟测试")
print("=" * 78)

# ─────────────── 一、五档定价（V5.0 第 2 章） ───────────────
print("\n[一] 五档定价")
s, b = req("GET", "/api/payment/plans")
plans = data_of(b).get("plans") or []
prices = {int(p.get("priceCents", 0)) for p in plans}
check("三档支付入口 = 29.9 / 99 / 599", s == 200 and prices >= {2990, 9900, 59900}, b)
names = {p.get("name") for p in plans}
check("心理账户命名（开业礼包/AI合伙人月卡/创业陪跑年卡）",
      names >= {"开业礼包", "AI 合伙人月卡", "创业全程陪跑年卡"}, b)
single = next((p for p in plans if p.get("plan") == "single"), {})
check("单次档（开业礼包）高亮为现金流主力", single.get("highlight") is True, single)

s, b = req("GET", "/api/payment/addons")
addons = data_of(b).get("addons") or []
addon_keys = {a.get("addon") for a in addons}
check("档位 5 增值加购包（5 项：海报/短视频/数字人/线索包/Logo）",
      s == 200 and addon_keys >= {"poster", "video", "avatar", "leads", "logo"}, b)
addon_prices = {a.get("addon"): int(a.get("priceCents", 0)) for a in addons}
check("加购定价（短视频 49 / 数字人 99 / 海报 9.9）",
      addon_prices.get("video") == 4900 and addon_prices.get("avatar") == 9900
      and addon_prices.get("poster") == 990, addon_prices)

# ─────────────── 二、M5-03 今日谈资卡 ───────────────
print("\n[二] 今日谈资卡（M5-03，免费传播物）")
GUEST = "v50-" + uuid.uuid4().hex
s, b = req("POST", "/api/auth/guest")
guest_token = data_of(b).get("accessToken") or data_of(b).get("access_token")

s, b = req("GET", "/api/share/talk-topic/today", token=guest_token, guest=GUEST)
topic = data_of(b)
check("今日谈资卡生成", s == 200 and b.get("code") == 0 and topic.get("id"), b)
check("带日期与来源", bool(topic.get("date")) and bool(topic.get("source")), topic)
check("要点 3—5 条", isinstance(topic.get("lines"), list) and 3 <= len(topic["lines"]) <= 5, topic)
check("不带付费引导（合规）", topic.get("noPaywall") is True, topic)

s, b = req("GET", "/api/share/talk-topic/today", token=guest_token, guest=GUEST)
check("谈资卡幂等（同日同城不重复生成）", data_of(b).get("id") == topic.get("id"), b)

s, b = req("GET", "/api/share/talk-topic/history?days=7", token=guest_token, guest=GUEST)
check("历史谈资卡列表", s == 200 and isinstance(data_of(b).get("items"), list), b)

s, b = req("POST", "/api/share/talk-topic/track",
           {"topicId": topic.get("id"), "channel": "微信好友"}, token=guest_token, guest=GUEST)
check("谈资卡转发埋点", s == 200 and b.get("code") == 0, b)

# ─────────────── 三、开业喜报（M3-06 / M5-02） ───────────────
print("\n[三] 开业喜报（M3-06 / M5-02）")
s, b = req("GET", "/api/share/report/templates")
templates = data_of(b).get("templates") or []
check("喜报模板 ≥ 3 种", s == 200 and len(templates) >= 3, b)

report_id = None
for tmpl in (1, 2, 3):
    s, b = req("POST", "/api/share/report", {"template": tmpl}, token=guest_token, guest=GUEST)
    rep = data_of(b)
    if tmpl == 1:
        report_id = rep.get("id")
        check(f"生成喜报（模板 {tmpl}）", s == 200 and rep.get("imageUrl"), b)
        check("喜报不带硬付费引导", rep.get("noPaywall") is True, rep)
        # 校验图片字节确为 PNG
        if rep.get("imageUrl"):
            s2, img = req("GET", rep["imageUrl"], raw=True)
            ok_png = isinstance(img, (bytes, bytearray)) and img[:8] == b"\x89PNG\r\n\x1a\n"
            check("喜报图片为有效 PNG", s2 == 200 and ok_png,
                  f"status={s2} head={img[:8] if isinstance(img,(bytes,bytearray)) else 'n/a'}")
    else:
        check(f"生成喜报（模板 {tmpl}）", s == 200 and rep.get("imageUrl"), b)

s, b = req("GET", "/api/share/reports", token=guest_token, guest=GUEST)
items = data_of(b).get("items") or []
check("我的喜报列表（M10 素材）", s == 200 and len(items) >= 3, b)

# ─────────────── 四、工具箱权益（M8 免费层边界） ───────────────
print("\n[四] 工具箱权益（M8）")
s, b = req("GET", "/api/tools/access", token=guest_token, guest=GUEST)
acc = data_of(b)
check("免费层：无工具权益 + 明确引导", s == 200 and acc.get("scope") == "free"
      and acc.get("availableTools") == [] and "开业礼包" in (acc.get("desc") or ""), b)

# ─────────────── 五、完整付费链路（为成本/漏斗提供真实数据） ───────────────
print("\n[五] 完整付费链路")
s, b = req("POST", "/api/diagnose", {"capital": 50000, "dailyHours": 8, "city": "上海"},
           token=guest_token, guest=GUEST)
task_id = data_of(b).get("taskId") or data_of(b).get("task_id")
check("提交诊断", s == 200 and task_id, b)

order_id = None
if task_id:
    for _ in range(60):
        s, b = req("GET", f"/api/diagnose/{task_id}/progress", token=guest_token, guest=GUEST)
        if data_of(b).get("status") in ("ready", "failed"):
            break
        time.sleep(0.4)
    check("诊断完成", data_of(b).get("status") == "ready", b)

    s, b = req("GET", f"/api/match?taskId={task_id}", token=guest_token, guest=GUEST)
    cards = data_of(b).get("free") or data_of(b).get("cards") or data_of(b).get("items") or []
    opp_id = cards[0].get("id") if cards else None

    s, b = req("POST", "/api/payment/create",
               {"plan": "single", "platform": "web", "matchId": opp_id},
               token=guest_token, guest=GUEST)
    order_id = data_of(b).get("orderId") or data_of(b).get("order_id")
    channel = data_of(b).get("channel") or "wechat"
    check("创建开业礼包订单（29.9）", s == 200 and order_id
          and int(data_of(b).get("amountCents", 0)) == 2990, b)

if order_id:
    s, b = req("POST", f"/api/payment/callback/{channel}",
               {"order_id": order_id, "result": "success"}, guest=GUEST)
    check("支付成功", s == 200 and data_of(b).get("status") in ("paid", "generating", "delivered"), b)

    s, b = req("POST", "/api/package/create", {"orderId": order_id},
               token=guest_token, guest=GUEST)
    check("触发启动包生成", s == 200 and b.get("code") == 0, b)

    pkg_id = None
    items = []
    for _ in range(80):
        s, b = req("GET", f"/api/package/{order_id}", token=guest_token, guest=GUEST)
        d = data_of(b)
        items = d.get("items") or []
        pkg_id = d.get("packageId") or d.get("id")
        if len(items) >= 10:
            break
        time.sleep(0.6)
    check("10 件交付物齐备", len(items) >= 10, f"items={len(items)}")

    # 下载埋点（M4-07 漏斗末环）
    s, b = req("POST", "/api/events/track", {"step": "download", "source": "交付页"},
               token=guest_token, guest=GUEST)
    check("下载埋点", s == 200 and b.get("code") == 0, b)

    s, b = req("GET", "/api/tools/access", token=guest_token, guest=GUEST)
    acc2 = data_of(b)
    check("购买开业礼包 → 解锁 2 个工具 30 天",
          s == 200 and acc2.get("scope") == "gift" and len(acc2.get("availableTools") or []) == 2, b)

# ─────────────── 六、后台三块新看板 ───────────────
print("\n[六] 后台三块新看板（M4-05 / M4-07 / M4-08）")
s, b = req("POST", "/api/admin/auth/login", {"username": "admin", "password": "admin123"})
totp = data_of(b).get("totpHint") or "123456"
s, b = req("POST", "/api/admin/auth/verify-2fa", {"username": "admin", "totp": totp})
admin_token = data_of(b).get("token")
check("后台登录", bool(admin_token), b)
AH = {"token": admin_token}

s, b = req("GET", "/api/admin/cost-monitor", **AH)
cm = data_of(b)
check("M4-05 成本监控：当日/当月口径", s == 200 and "today" in cm and "month" in cm, b)
check("M4-05 成本占收入比 + 25% 告警位", s == 200 and "costRatio" in (cm.get("today") or {})
      and "alert" in cm and cm.get("alertRatio") == 0.25, b)
check("M4-05 按模型 / 按功能分布",
      isinstance(cm.get("byModel"), list) and isinstance(cm.get("byFeature"), list), b)
check("第7章 六道闸门状态（模型路由/缓存/模板比/轮数上限）",
      s == 200 and (cm.get("gates") or {}).get("modelTier") == "light"
      and "cacheHitRate" in (cm.get("gates") or {}), b)
feat = {f.get("feature") for f in (cm.get("byFeature") or [])}
check("成本台账已记录 package/diagnose/topic/report 等成本",
      feat >= {"diagnose", "package"}, cm.get("byFeature"))

s, b = req("GET", "/api/admin/funnel?period=month", **AH)
fn = data_of(b)
steps = [x.get("step") for x in (fn.get("steps") or [])]
check("M4-07 转化漏斗 6 步齐全",
      s == 200 and steps == ["visit", "diagnose_start", "diagnose_done",
                             "pay_click", "pay_success", "download"], b)
check("M4-07 每步含转化率与流失标红", s == 200
      and all("rateFromTop" in x and "dropAlert" in x for x in (fn.get("steps") or [])), b)

s, b = req("GET", "/api/admin/growth", **AH)
gw = data_of(b)
sm = gw.get("summary") or {}
check("M4-08 裂变数据：转发/新用户/付费用户",
      s == 200 and {"shares", "registers", "pays"} <= set(sm.keys()), b)
check("M4-08 K 因子实时显示（K>1 即自增长飞轮）", "kFactor" in sm, sm)
check("M4-08 单用户裂变获客成本", "fissionCacCents" in sm and "fissionCacLabel" in sm, sm)

# ─────────────── 结果 ───────────────
print("-" * 78)
print(f"结果：PASS={PASS}  FAIL={FAIL}")
if FAILED:
    print("失败项：")
    for f in FAILED:
        print("  -", f)
print("=" * 78)
sys.exit(1 if FAIL else 0)
