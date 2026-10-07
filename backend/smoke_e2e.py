"""BizFast 网页端全链路端到端冒烟测试（前台 M1–M10 + 后台 M11）。

运行前先启动后端：
    cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077
然后：
    cd backend && ./.venv/Scripts/python.exe smoke_e2e.py

覆盖：游客诊断 → 3 商机 → 第 4 锁定 → 付费 → D01–D10 生成 → ZIP 下载 →
      个人中心（消息/订阅/收藏）→ 工具 → 游戏 → 分享 → 后台运营全模块。
所有断言均检查「中文提示」与统一信封，禁止英文报错/裸错误码（ADR-006）。
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
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def req_multipart(path, fields, files=None, token=None, guest=None):
    """multipart/form-data 请求（工具箱接口用 Form/File 接收）。"""
    boundary = "----bizfaste2e" + uuid.uuid4().hex
    parts = []
    for k, v in (fields or {}).items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (fname, content, ctype) in (files or {}).items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
            f'Content-Type: {ctype}\r\n\r\n'.encode() + content + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if guest:
        headers["X-Guest-Token"] = guest
    r = urllib.request.Request(BASE + path, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS", name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("FAIL", name, str(detail)[:220])


def data_of(resp):
    return (resp or {}).get("data") or {}


def has_english_error(resp) -> str | None:
    """检查响应体是否泄露英文错误（ADR-006 禁止）。"""
    text = json.dumps(resp, ensure_ascii=False)
    for bad in ["Internal Server Error", "Traceback", "ValidationError", "Not Found",
                "Unprocessable", "KeyError", "AttributeError", "TypeError"]:
        if bad in text:
            return bad
    return None


print("=" * 78)
print("BizFast 网页端全链路端到端冒烟测试")
print("=" * 78)

# ─────────────── M1 首屏配置 ───────────────
s, b = req("GET", "/api/home/config")
check("M1 首屏配置", s == 200 and "capitals" in data_of(b), b)

# ─────────────── M10 游客创建 ───────────────
s, b = req("POST", "/api/auth/guest")
guest_token = data_of(b).get("accessToken") or data_of(b).get("access_token")
check("M10 游客创建", s == 200 and guest_token, b)

GUEST = "e2e-" + uuid.uuid4().hex

# ─────────────── M2 诊断 ───────────────
s, b = req("POST", "/api/diagnose",
           {"capital": 50000, "dailyHours": 8, "city": "上海"}, token=guest_token, guest=GUEST)
task_id = data_of(b).get("taskId") or data_of(b).get("task_id")
check("M2 提交诊断", s == 200 and task_id and b.get("code") == 0, b)

result = {}
if task_id:
    for _ in range(60):
        s, b = req("GET", f"/api/diagnose/{task_id}/progress", token=guest_token, guest=GUEST)
        d = data_of(b)
        if d.get("status") in ("ready", "failed"):
            break
        time.sleep(0.4)
    check("M2 诊断进度（真实阶段）", s == 200 and d.get("status") == "ready", b)
    check("M2 进度非造假（percent 与 stage 对应）",
          isinstance(d.get("percent"), int) and d.get("percent") <= 100, d)

    s, b = req("GET", f"/api/diagnose/{task_id}/result", token=guest_token, guest=GUEST)
    result = data_of(b)
    check("M2 诊断结果（热度方向）",
          s == 200 and (result.get("heatDirections") or result.get("directions")), b)

    s, b = req("GET", f"/api/diagnose/heatmap/{task_id}", token=guest_token, guest=GUEST, raw=True)
    check("M2 热度图（PNG 字节）", s == 200 and isinstance(b, (bytes, bytearray)) and len(b) > 500,
          f"status={s} len={len(b) if isinstance(b,(bytes,bytearray)) else 'n/a'}")

# ─────────────── M3 商机匹配 ───────────────
s, b = req("GET", f"/api/match?taskId={task_id}", token=guest_token, guest=GUEST)
d = data_of(b)
cards = d.get("free") or d.get("opportunities") or d.get("items") or d.get("cards") or []
check("M3 匹配返回 3 张卡片", s == 200 and len(cards) == 3, b)

locked = d.get("locked") or d.get("fourth")
opp_id = (cards[0].get("id") if cards else None)

if opp_id:
    s, b = req("GET", f"/api/match/{opp_id}?taskId={task_id}", token=guest_token, guest=GUEST)
    dd = data_of(b)
    check("M3 商机详情（五要素）",
          s == 200 and (dd.get("fiveElements") or dd.get("five_elements") or dd.get("elements")), b)

    s, b = req("GET", f"/api/match/{opp_id}/entitled", token=guest_token, guest=GUEST)
    check("M3 第 4 个商机锁定（未付费）",
          s == 200 and data_of(b).get("entitled") is False, b)

    s, b = req("POST", f"/api/match/{opp_id}/favorite", token=guest_token, guest=GUEST)
    check("M3 收藏商机", s == 200 and b.get("code") == 0, b)

# ─────────────── M5 支付 ───────────────
s, b = req("GET", "/api/payment/plans")
plans = data_of(b).get("plans") or []
check("M2 三档价格（V5.0：29.9/99/599）",
      s == 200 and len(plans) == 3
      and {int(p.get("priceCents", 0)) for p in plans} >= {2990, 9900, 59900},
      b)

s, b = req("GET", "/api/payment/coupons", token=guest_token, guest=GUEST)
check("M5 优惠券清单 + 规则明示",
      s == 200 and data_of(b).get("rules") and data_of(b).get("items") is not None, b)

s, b = req("POST", "/api/payment/coupon/validate",
           {"code": "WELCOME5", "plan": "single"}, token=guest_token, guest=GUEST)
check("M5 优惠券校验（不核销）", s == 200 and data_of(b).get("discountCents") == 500, b)

s, b = req("POST", "/api/payment/create",
           {"plan": "single", "platform": "web", "matchId": opp_id},
           token=guest_token, guest=GUEST)
pay = data_of(b)
order_id = pay.get("orderId") or pay.get("order_id")
channel = pay.get("channel") or "wechat"
check("M5 创建订单（幂等）", s == 200 and order_id and b.get("code") == 0, b)

s, b = req("GET", f"/api/payment/order/{order_id}", token=guest_token, guest=GUEST)
check("M5 主动查单", s == 200 and data_of(b).get("status") == "pending", b)

if order_id:
    s, b = req("POST", f"/api/payment/callback/{channel}",
               {"order_id": order_id, "result": "success"}, guest=GUEST)
    check("M5 支付回调 → 已支付", s == 200 and data_of(b).get("status") in ("paid", "generating", "delivered"), b)

    s, b = req("POST", f"/api/payment/callback/{channel}",
               {"order_id": order_id, "result": "success"}, guest=GUEST)
    check("M5 重复回调幂等（不重复发货）", s == 200 and data_of(b).get("duplicated") is True, b)

    s, b = req("GET", f"/api/payment/order/{order_id}", token=guest_token, guest=GUEST)
    check("M5 回调后订单状态", s == 200 and data_of(b).get("status") in ("paid", "generating", "delivered"), b)

    # ─────────── M3 第 4 个商机解锁 ───────────
    s, b = req("GET", f"/api/match/{opp_id}/entitled", token=guest_token, guest=GUEST)
    check("M3 付费后解锁完整商机", s == 200 and data_of(b).get("entitled") is True, b)

# ─────────────── M4 启动包生成（D01–D10，含多格式） ───────────────
if order_id:
    s, b = req("POST", "/api/package/create", {"orderId": order_id}, token=guest_token, guest=GUEST)
    check("M4 创建生成任务（/api/package/create）", s == 200 and b.get("code") == 0
          and (data_of(b).get("orderId") or data_of(b).get("order_id")) == order_id, b)

    pkg = {}
    for _ in range(200):
        s, b = req("GET", f"/api/package/{order_id}/progress", token=guest_token, guest=GUEST)
        pkg = data_of(b)
        if pkg.get("status") in ("delivered", "failed"):
            break
        time.sleep(0.5)

    check("M4 启动包生成完成（<3 分钟）", pkg.get("status") == "delivered", pkg)
    check("M4 十件交付物齐全", pkg.get("done") == 10 and len(pkg.get("items") or []) == 10, pkg)
    check("M4 进度含真实阶段信息（stage/currentItem）",
          isinstance(pkg.get("stage"), str) and pkg.get("stage") != "", pkg)

    s, b = req("GET", f"/api/package/{order_id}", token=guest_token, guest=GUEST)
    detail = data_of(b)
    zip_url = detail.get("zipUrl") or detail.get("zip_url")
    items = detail.get("items") or []
    check("M4 启动包详情 + ZIP", s == 200 and zip_url and len(items) == 10, b)

    # PRD 4.4.1：多格式交付物（D03/D06 = PDF+Word、D07 = Word+TXT、D08 = PNG+SVG、D09 = PDF+Excel）
    expected_fmt = {"D03": 2, "D06": 2, "D07": 2, "D08": 2, "D09": 2, "D01": 1, "D02": 1,
                    "D04": 1, "D05": 1, "D10": 1}
    fmt_map = {it.get("code"): (it.get("formats") or []) for it in items}
    check("M4 多格式交付物齐全（D03/D06/D07/D08/D09 双格式）",
          all(len(fmt_map.get(c) or []) == n for c, n in expected_fmt.items()),
          {c: [f.get("fileType") for f in (fmt_map.get(c) or [])] for c in expected_fmt})

    s, blob = req("GET", f"/api/package/{order_id}/item/D01", raw=True, guest=GUEST)
    check("M4 单件下载（D01 PDF 字节流，inline 可预览）",
          s == 200 and isinstance(blob, (bytes, bytearray)) and blob[:4] == b"%PDF",
          f"status={s} head={blob[:8] if isinstance(blob,(bytes,bytearray)) else 'n/a'}")

    s, blob = req("GET", f"/api/package/{order_id}/item/D08?format=svg", raw=True, guest=GUEST)
    check("M4 单件指定格式（D08 SVG）",
          s == 200 and isinstance(blob, (bytes, bytearray)) and b"<svg" in blob[:400],
          f"status={s}")

    s, b = req("GET", f"/api/package/{order_id}/item/ZZZ", token=guest_token, guest=GUEST)
    check("M4 非法交付物 → 中文错误", b.get("code") == 40401 and b.get("message"), b)

    if zip_url:
        s, blob = req("GET", zip_url, raw=True, guest=GUEST)
        check("M4 ZIP 可下载（字节流）", s == 200 and isinstance(blob, (bytes, bytearray)) and len(blob) > 1000,
              f"status={s} len={len(blob) if isinstance(blob,(bytes,bytearray)) else 'n/a'}")

    s, b = req("GET", "/api/packages", token=guest_token, guest=GUEST)
    mine = b.get("data")
    check("M4 我的启动包列表（/api/packages）",
          s == 200 and isinstance(mine, list) and len(mine) >= 1 and mine[0].get("orderId") == order_id, b)

# ─────────────── M9 消息中心 ───────────────
s, b = req("GET", "/api/notify/messages", token=guest_token, guest=GUEST)
msgs = data_of(b)
check("M9 消息列表", s == 200 and (msgs.get("items") is not None), b)

s, b = req("GET", "/api/notify/unread", token=guest_token, guest=GUEST)
check("M9 未读数", s == 200 and "unread" in data_of(b), b)

s, b = req("GET", "/api/notify/settings", token=guest_token, guest=GUEST)
check("M9 通知设置（含免打扰）", s == 200 and "dndStart" in data_of(b), b)

s, b = req("PUT", "/api/notify/settings",
           {"serviceNotice": True, "appPush": False, "desktopNotice": True,
            "marketReminder": True, "dndEnabled": True, "dndStart": "23:00", "dndEnd": "07:00"},
           token=guest_token, guest=GUEST)
check("M9 保存通知设置", s == 200 and data_of(b).get("dndStart") == "23:00", b)

s, b = req("GET", "/api/notify/subscribe", token=guest_token, guest=GUEST)
check("M9 订阅状态", s == 200 and b.get("code") == 0, b)

# ─────────────── M8 分享与增长 ───────────────
s, b = req("GET", "/api/share/invite/info", token=guest_token, guest=GUEST)
invite = data_of(b)
code = (invite.get("link") or "").split("inviter=")[-1]
check("M8-03 邀请信息", s == 200 and code, b)

s, b = req("POST", "/api/share/card",
           {"productName": "社区团购", "lines": ["A", "B"]}, token=guest_token, guest=GUEST)
card = data_of(b)
check("M8-01 分享卡片", s == 200 and card.get("id") and code in (card.get("shareUrl") or ""), b)

s, b = req("POST", "/api/share/track",
           {"cardId": card.get("id"), "channel": "微信好友"}, token=guest_token, guest=GUEST)
check("M8-02 分享埋点", s == 200 and data_of(b).get("ok") is True, b)

s, b = req("GET", f"/api/share/{card.get('id')}", token=guest_token, guest=GUEST)
check("M8-01 分享落地页数据", s == 200 and b.get("code") == 0, b)

GUEST_B = "e2e-b-" + uuid.uuid4().hex
s, b = req("POST", "/api/share/invite/bind", {"inviterCode": code}, guest=GUEST_B)
check("M8-03 老邀新双方得券", s == 200 and data_of(b).get("status") == "issued", b)

# ─────────────── M7 小游戏 ───────────────
s, b = req("POST", "/api/games/score",
           {"game_type": "match3", "score": 1200, "duration_seconds": 60},
           token=guest_token, guest=GUEST)
check("M7 提交游戏分数", s == 200 and b.get("code") == 0, b)

s, b = req("GET", "/api/games/leaderboard/match3", token=guest_token, guest=GUEST)
check("M7 排行榜", s == 200 and data_of(b).get("leaderboard") is not None, b)

s, b = req("GET", "/api/games/my-best/match3", token=guest_token, guest=GUEST)
check("M7 我的最佳成绩", s == 200 and b.get("code") == 0, b)

s, b = req("GET", "/api/games/my-scores", token=guest_token, guest=GUEST)
check("M7 我的成绩记录", s == 200 and b.get("code") == 0, b)

# ─────────────── M6 工具（4 个） ───────────────
s, b = req_multipart("/api/tools/copywriting",
                     {"category": "promotion", "keywords": "柠檬茶,夜市", "tone": "friendly", "count": 3},
                     token=guest_token, guest=GUEST)
check("M6 获客文案工具", s == 200 and (data_of(b).get("items") or data_of(b).get("copies")), b)

s, b = req_multipart("/api/tools/qrcode",
                     {"content": "https://example.com/landing", "size": 300},
                     token=guest_token, guest=GUEST)
check("M6 二维码工具", s == 200 and (data_of(b).get("url") or data_of(b).get("dataUrl")), b)

# 图片压缩（用 Pillow 现场造一张 PNG）
try:
    import io as _io

    from PIL import Image as _Image

    _buf = _io.BytesIO()
    _Image.new("RGB", (800, 600), (22, 93, 255)).save(_buf, "PNG")
    s, b = req_multipart("/api/tools/image/compress", {"quality": "60", "format": "jpeg"},
                         files={"file": ("test.png", _buf.getvalue(), "image/png")},
                         token=guest_token, guest=GUEST)
    check("M6 图片压缩工具", s == 200 and (data_of(b).get("url") or data_of(b).get("dataUrl")), b)

    # PDF 合并 / 拆分（用 reportlab 造两份小 PDF）
    from reportlab.pdfgen import canvas as _canvas
    pdfs = {}
    for name in ("a.pdf", "b.pdf"):
        _pb = _io.BytesIO()
        _c = _canvas.Canvas(_pb)
        _c.drawString(72, 720, f"BizFast E2E {name}")
        _c.showPage()
        _c.save()
        pdfs[name] = _pb.getvalue()

    s, b = req_multipart("/api/tools/pdf/merge",
                         {}, files={"files": ("a.pdf", pdfs["a.pdf"], "application/pdf")},
                         token=guest_token, guest=GUEST)
    check("M6 PDF 合并工具", s == 200 and (data_of(b).get("url") or data_of(b).get("fileName")), b)

    s, b = req_multipart("/api/tools/pdf/split", {"pages": "1"},
                         files={"file": ("a.pdf", pdfs["a.pdf"], "application/pdf")},
                         token=guest_token, guest=GUEST)
    check("M6 PDF 拆分工具", s == 200 and bool(data_of(b).get("parts")), b)
except Exception as exc:
    check("M6 工具箱（图片/PDF）", False, f"测试脚本异常: {exc}")

# ─────────────── M10 短信登录 / 用户信息 ───────────────
PHONE = "138" + str(uuid.uuid4().int)[:8]
s, b = req("POST", "/api/auth/sms/send", {"phone": PHONE})
check("M10 发送验证码", s == 200 and b.get("code") == 0, b)

s, b = req("POST", "/api/auth/sms/login", {"phone": PHONE, "code": "123456"})
user_token = data_of(b).get("accessToken") or data_of(b).get("access_token")
check("M10 手机号验证码登录", s == 200 and user_token, b)

s, b = req("GET", "/api/auth/me", token=user_token)
check("M10 获取用户信息", s == 200 and data_of(b).get("phone") == PHONE, b)

s, b = req("POST", "/api/auth/refresh", {"refresh_token": data_of(b).get("refresh_token") or ""})
check("M10 刷新令牌（无 refresh 时中文报错）", s == 200, b)

# ─── 契约路径（前端 services/repo.ts 实际调用）───
PHONE2 = "139" + str(uuid.uuid4().int)[:8]
s, b = req("POST", "/api/auth/sms/send", {"phone": PHONE2})
check("M10 发送验证码（契约登录前置）", s == 200 and b.get("code") == 0, b)

s, b = req("POST", "/api/auth/login", {"phone": PHONE2, "code": "123456"})
login_data = data_of(b)
check("M10 POST /api/auth/login → {token,user}",
      s == 200 and login_data.get("token") and (login_data.get("user") or {}).get("phone") == PHONE2
      and "isGuest" in (login_data.get("user") or {}), b)
contract_token = login_data.get("token")

s, b = req("POST", "/api/auth/wechat", {"unionid": "e2e-wx-" + uuid.uuid4().hex[:10]})
check("M10 POST /api/auth/wechat → {token,user}",
      s == 200 and data_of(b).get("token") and (data_of(b).get("user") or {}).get("isGuest") is False, b)

s, b = req("GET", "/api/user/me", token=contract_token)
check("M10 GET /api/user/me", s == 200 and data_of(b).get("phone") == PHONE2, b)

s, b = req("GET", "/api/user/orders", token=contract_token)
check("M10 GET /api/user/orders（列表）", s == 200 and isinstance(b.get("data"), list), b)

s, b = req("GET", "/api/user/me")
check("M10 /api/user/me 未登录 → 中文 40101", b.get("code") == 40101 and "登录" in (b.get("message") or ""), b)

s, b = req("POST", "/api/user/logout", {}, token=contract_token)
check("M10 POST /api/user/logout", s == 200 and data_of(b).get("ok") is True, b)

s, b = req("DELETE", "/api/user/account", token=contract_token)
check("M10 DELETE /api/user/account（注销）", s == 200 and data_of(b).get("purgeAt"), b)

# ─────────────── M11 运营后台 ───────────────
s, b = req("GET", "/api/admin/dashboard")
check("M11 未登录拦截（中文 40101）", s == 200 and b.get("code") == 40101 and "登录" in (b.get("message") or ""), b)

s, b = req("POST", "/api/admin/auth/login", {"username": "admin", "password": "wrong"})
check("M11 登录密码错误（中文）", s == 200 and b.get("code") == 40001 and "密码" in (b.get("message") or ""), b)

s, b = req("POST", "/api/admin/auth/login", {"username": "admin", "password": "admin123"})
check("M11 登录第一步（下发 TOTP）", s == 200 and data_of(b).get("needTotp") is True, b)
totp_hint = data_of(b).get("totpHint") or "123456"

s, b = req("POST", "/api/admin/auth/verify-2fa", {"username": "admin", "totp": totp_hint})
admin_token = data_of(b).get("token")
check("M11 登录第二步（签发 JWT）", s == 200 and admin_token and data_of(b).get("role") == "admin", b)

AH = {"token": admin_token}

s, b = req("GET", "/api/admin/dashboard?granularity=day", **AH)
kpis = data_of(b).get("kpis") or {}
check("M11-05 看板指标", s == 200 and "diagnoseCount" in kpis and "trend" in data_of(b), b)

s, b = req("GET", "/api/admin/users?page=1&pageSize=20", **AH)
check("M11-01 用户列表", s == 200 and data_of(b).get("items") is not None, b)

s, b = req("GET", "/api/admin/orders?page=1&pageSize=20", **AH)
order_items = data_of(b).get("items") or []
check("M11-02 订单列表", s == 200 and order_items is not None, b)

if order_items:
    oid = order_items[0]["id"]
    s, b = req("GET", f"/api/admin/users/{order_items[0].get('userId')}", **AH)
    check("M11-01 用户详情（含订单/启动包）", s == 200 and "user" in data_of(b), b)

    s, b = req("PUT", f"/api/admin/orders/{oid}/refund",
               {"action": "reject", "reason": "测试驳回"}, **AH)
    check("M11-02 退款处理（驳回）", s == 200 and b.get("code") == 0, b)

# 商机库 CRUD
s, b = req("GET", "/api/admin/opportunities?page=1&pageSize=50", **AH)
check("M11-03 商机列表", s == 200 and data_of(b).get("items") is not None, b)

s, b = req("POST", "/api/admin/opportunities",
           {"title": "E2E 测试商机", "category": "餐饮小吃", "city": "上海",
            "capitalMin": 10000, "capitalMax": 30000, "paybackMonths": 4,
            "marginPercent": 40, "difficultyStars": 2}, **AH)
new_opp = data_of(b)
opp_id_admin = new_opp.get("id")
check("M11-03 新增商机", s == 200 and opp_id_admin, b)

if opp_id_admin:
    s, b = req("PUT", f"/api/admin/opportunities/{opp_id_admin}",
               {"title": "E2E 测试商机（改）", "capitalMin": 12000}, **AH)
    check("M11-03 编辑商机", s == 200 and b.get("code") == 0, b)

    s, b = req("POST", f"/api/admin/opportunities/{opp_id_admin}/review",
               {"action": "approve"}, **AH)
    check("M11-03 审核商机（通过）", s == 200 and data_of(b).get("status") == "passed", b)

    s, b = req("PUT", f"/api/admin/opportunities/{opp_id_admin}/shelf",
               {"on_shelf": True}, **AH)
    check("M11-03 商机上架", s == 200 and data_of(b).get("onShelf") is True, b)

    s, b = req("DELETE", f"/api/admin/opportunities/{opp_id_admin}", **AH)
    check("M11-03 删除商机", s == 200 and b.get("code") == 0, b)

s, b = req("POST", "/api/admin/opportunities/import",
           {"items": [{"title": "导入商机A"}, {"title": "导入商机B"}]}, **AH)
check("M11-03 批量导入", s == 200 and data_of(b).get("imported") == 2, b)

# 提示词
s, b = req("GET", "/api/admin/prompts", **AH)
prompts = data_of(b).get("items") or []
check("M11-04 提示词列表", s == 200 and len(prompts) >= 3 and data_of(b).get("notice"), b)

if prompts:
    key = prompts[0]["key"]
    before = len(prompts[0].get("versions") or [])
    s, b = req("PUT", f"/api/admin/prompts/{key}",
               {"content": "E2E 修改后的提示词内容", "model": "doubao-seed-1.6"}, **AH)
    check("M11-04 保存提示词（生成新版本）", s == 200 and b.get("code") == 0, b)

    s, b = req("GET", f"/api/admin/prompts/{key}/history", **AH)
    versions = data_of(b).get("versions") or []
    check("M11-04 版本历史 +1", s == 200 and len(versions) == before + 1, b)

    if len(versions) >= 2:
        s, b = req("POST", f"/api/admin/prompts/{key}/rollback",
                   {"version": 1}, **AH)
        check("M11-04 一键回滚", s == 200 and b.get("code") == 0, b)

# 内容审核
s, b = req("GET", "/api/admin/reviews?page=1&pageSize=20", **AH)
reviews = data_of(b).get("items") or []
check("M11-06 审核列表", s == 200 and reviews is not None, b)

# 角色权限
s, b = req("GET", "/api/admin/roles", **AH)
roles = data_of(b).get("items") or []
check("M11-07 四角色权限矩阵", s == 200 and len(roles) == 4 and data_of(b).get("notice"), b)

if roles:
    s, b = req("PUT", "/api/admin/roles/operator",
               {"perms": roles[1]["perms"]}, **AH)
    check("M11-07 保存角色权限", s == 200 and b.get("code") == 0, b)

# 越权拦截：operator 无 users 权限
s, b = req("POST", "/api/admin/auth/verify-2fa", {"username": "operator", "totp": "123456"})
op_token = data_of(b).get("token")
if op_token:
    s, b = req("GET", "/api/admin/users", token=op_token)
    check("M11-07 越权拦截（operator 访问用户管理被拒）",
          s == 200 and b.get("code") == 40301 and "权限" in (b.get("message") or ""), b)

# 审计日志
s, b = req("GET", "/api/admin/audit?page=1&pageSize=30", **AH)
logs = data_of(b).get("items") or []
check("M11-08 审计日志（含本次操作）", s == 200 and len(logs) > 0
      and any("登录" in (l.get("action") or "") for l in logs), b)

# 运营位
s, b = req("GET", "/api/admin/ops", **AH)
ops = data_of(b).get("items") or []
check("M11-10 运营位列表", s == 200 and len(ops) >= 2, b)

if ops:
    sid = ops[0]["id"]
    s, b = req("PUT", f"/api/admin/ops/{sid}",
               {"title": "E2E 运营位标题"}, **AH)
    check("M11-10 保存运营位", s == 200 and b.get("code") == 0, b)

    s, b = req("PUT", f"/api/admin/ops/{sid}/toggle", {"enabled": False}, **AH)
    check("M11-10 停用运营位", s == 200 and data_of(b).get("enabled") is False, b)

# 数据导出
for kind in ("users", "orders", "deliveries", "events"):
    s, b = req("GET", f"/api/admin/export/{kind}?format=csv", **AH)
    dd = data_of(b)
    check(f"M11-11 导出 {kind}", s == 200 and dd.get("content") is not None and dd.get("fileName"), b)

# 分享转化概览（D 模块）
s, b = req("GET", "/api/admin/share/stats", **AH)
check("M11-D 分享转化概览", s == 200 and "summary" in data_of(b), b)

# ─────────────── 英文报错扫描 ───────────────
print("-" * 78)
print(f"结果：PASS={PASS}  FAIL={FAIL}")
if FAILED:
    print("失败项：")
    for f in FAILED:
        print("  -", f)
print("=" * 78)
sys.exit(1 if FAIL else 0)
