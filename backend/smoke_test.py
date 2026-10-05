"""D 端冒烟测试（M1 首屏配置 + M8 分享与增长 + M11-D 分享转化概览）。

注意：登录/账号后端（M10 auth、/api/user/*）归研发 A；运营后台登录（M11）归研发 B。
本脚本只验证 D 认领的端点：
- GET  /api/home/config            (M1)
- POST /api/share/card             (M8-01)
- GET  /api/share/{id}             (M8-01)
- POST /api/share/track            (M8-02)
- GET  /api/share/invite/info      (M8-03)
- POST /api/share/invite/bind      (M8-03 双方得券)
- GET  /api/admin/share/stats      (M11-D，需 admin/operator/support 角色 token)
运行前请先启动后端：uvicorn app.main:app --port 8016
"""
import asyncio
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8077"

# 让本脚本能 import app（用于签发管理员 token，验证 M11-D 成功路径）
sys.path.insert(0, r"D:\XiangMu\SoftwareDevelopmentEngineerD\BizFast\backend")


def req(method, path, body=None, token=None, guest=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if guest:
        headers["X-Guest-Token"] = guest
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL"), name, "" if cond else str(detail)[:160])


async def _mint_admin_token():
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_access_token
    from app.models import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.role == "admin"))).scalar_one_or_none()
        if u is None:
            u = User(
                id="smoke-admin-" + uuid.uuid4().hex,
                unionid="admin:smoke",
                role="admin",
                plan="none",
                invite_code="ADMIN",
            )
            db.add(u)
            await db.commit()
        return create_access_token(u.id)


# 0 探活
s, b = req("GET", "/api/home/config")
check("server-up", s == 200, b)

# 1 首屏配置
s, b = req("GET", "/api/home/config")
check("M1 home/config", s == 200 and "capitals" in (b.get("data") or {}), b)

GUEST_A = "smoke-a-" + uuid.uuid4().hex
GUEST_B = "smoke-b-" + uuid.uuid4().hex

# 2 邀请信息（确保 GUEST_A 有邀请码）
s, b = req("GET", "/api/share/invite/info", guest=GUEST_A)
ok = s == 200 and "inviter=" in (b.get("data") or {}).get("link", "")
code = (b.get("data") or {}).get("link", "").split("inviter=")[-1] if ok else ""
check("M8-03 invite/info", ok, b)

# 3 生成分享卡片（带邀请码）
s, b = req("POST", "/api/share/card", {"productName": "社区团购", "lines": ["A", "B"]}, guest=GUEST_A)
ok = s == 200 and code and code in (b.get("data") or {}).get("shareUrl", "")
card_id = (b.get("data") or {}).get("id")
check("M8 share/card 带邀请码", ok, b)

# 4 分享埋点
s, b = req("POST", "/api/share/track", {"cardId": card_id, "channel": "微信好友"}, guest=GUEST_A)
check("M8 share/track", s == 200 and (b.get("data") or {}).get("ok") is True, b)

# 5 邀请绑定（老邀新，双方得券）
s, b = req("POST", "/api/share/invite/bind", {"inviterCode": code}, guest=GUEST_B)
check("M8-03 bind 双方得券", s == 200 and (b.get("data") or {}).get("status") == "issued", b)

# 6 M11-D 分享转化概览（未授权 -> 中文 40101）
s, b = req("GET", "/api/admin/share/stats")
check("M11-D 未授权拦截", s == 200 and b.get("code") == 40101, b)

# 7 M11-D 分享转化概览（管理员 token，成功）
admin_token = asyncio.run(_mint_admin_token())
s, b = req("GET", "/api/admin/share/stats", token=admin_token)
check("M11-D admin/share/stats", s == 200 and "summary" in (b.get("data") or {}), b)

print("DONE")
