import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8014"


def req(method, path, body=None, token=None, retries=40):
    last = None
    for _ in range(retries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:
                return e.code, {}
        except Exception as e:
            last = e
            time.sleep(0.5)
    raise last


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL"), name, "" if cond else str(detail)[:160])


# 0 后台启动健康（/docs 返回 HTML，故用 JSON 端点探活）
s, b = req("GET", "/api/home/config")
check("server-up", s == 200, b)

# 1 首屏配置
s, b = req("GET", "/api/home/config")
check("M1 home/config", s == 200 and "capitals" in (b.get("data") or {}), b)

# 2 游客态 user/me
s, b = req("GET", "/api/user/me")
check("M10 guest user/me", s == 200 and (b.get("data") or {}).get("isGuest") is True, b)

# 3 手机号登录
s, b = req("POST", "/api/auth/login", {"phone": "13800001111", "code": "123456"})
check("M10 auth/login", s == 200 and (b.get("data") or {}).get("token"), b)
token = b["data"]["token"]
user = b["data"]["user"]

# 4 个人中心（脱敏）
s, b = req("GET", "/api/user/me", token=token)
check("M10 user/me 脱敏", s == 200 and b["data"]["phone"] == "138****01111", b)

# 5 订单
s, b = req("GET", "/api/user/orders", token=token)
check("M10 user/orders", s == 200 and isinstance(b.get("data"), list), b)

# 6 生成分享卡片
s, b = req("POST", "/api/share/card", {"productName": "社区团购", "lines": ["A", "B"]}, token=token)
check("M8 share/card 带邀请码", s == 200 and "inviter=" in (b.get("data") or {}).get("shareUrl", ""), b)
card_id = b["data"]["id"]

# 7 分享埋点
s, b = req("POST", "/api/share/track", {"cardId": card_id, "channel": "微信好友"}, token=token)
check("M8 share/track", s == 200 and (b.get("data") or {}).get("ok") is True, b)

# 8 邀请信息
s, b = req("GET", "/api/share/invite/info", token=token)
check("M8-03 invite/info", s == 200 and "inviter=" in (b.get("data") or {}).get("link", ""), b)

# 9 邀请绑定（老邀新，双方得券）
# 用第二个手机号登录，绑定第一个用户的邀请码
inviter = user.get("inviteCode")
s, b = req("POST", "/api/auth/login", {"phone": "13900002222", "code": "654321"})
invitee_token = b["data"]["token"]
s, b = req("POST", "/api/share/invite/bind", {"inviterCode": inviter}, token=invitee_token)
check("M8-03 bind 双方得券", s == 200 and (b.get("data") or {}).get("status") == "issued", b)

# 10 后台登录
s, b = req("POST", "/api/admin/login", {"username": "admin", "password": "admin123"})
check("M11 admin/login", s == 200 and (b.get("data") or {}).get("token"), b)
admin_token = b["data"]["token"]

# 11 分享转化概览（M11-D）
s, b = req("GET", "/api/admin/share/stats", token=admin_token)
check("M11-D admin/share/stats", s == 200 and "summary" in (b.get("data") or {}), b)

# 12 未授权访问后台 -> 中文 40101
s, b = req("GET", "/api/admin/share/stats")
check("M11-D 未授权拦截", s == 200 and b.get("code") == 40101, b)

# 13 注销账号
s, b = req("DELETE", "/api/user/account", token=token)
check("M10 注销账号", s == 200 and (b.get("data") or {}).get("purgeAt"), b)

print("DONE")
