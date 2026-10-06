"""M4 并发竞态回归测试。

复现并锁定原始缺陷：前台页面重复挂载 / 用户重复点击时，
`POST /api/package/create` 会在极短时间内被并发调用多次；修复前
每一次都通过了「启动包是否已存在」的检查，于是入队多次、生成多遍，
写出多条 `packages` 记录 —— 之后 `GET /{orderId}/progress` 用
`scalar_one_or_none()` 查询会抛 MultipleResultsFound，前端只看到
「服务开小差了，请重试」。

本脚本断言：
1. 6 个并发 create 请求全部返回 200 且 code=0（不出现 500）；
2. 生成完成后 packages 表中该订单**只有 1 行**；
3. deliverable_files 恰好 15 行（10 件交付物 / PRD 4.4.1 多格式）；
4. 并发轮询 progress 全部 200 且状态一致，最终 delivered；
5. 交付完成后重复 create 不会重新生成（幂等，仍为 1 行 / 15 文件）。

运行前先启动后端：
    cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8077
然后：
    cd backend && ./.venv/Scripts/python.exe smoke_race.py
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8077"
DB = Path(__file__).parent / "var" / "bizfast.db"

PASS = 0
FAIL = 0
FAILED: list[str] = []


def req(method, path, body=None, token=None, guest=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if guest:
        headers["X-Guest-Token"] = guest
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
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
        print("FAIL", name, str(detail)[:240])


def data_of(resp):
    return (resp or {}).get("data") or {}


def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return list(con.execute(sql, args))
    finally:
        con.close()


print("=" * 78)
print("BizFast M4 并发竞态回归测试")
print("=" * 78)

# ───────── 准备：游客 → 诊断 → 支付 ─────────
_, b = req("POST", "/api/auth/guest")
token = data_of(b).get("accessToken") or data_of(b).get("access_token")
GUEST = "race-" + uuid.uuid4().hex
check("准备：游客会话", bool(token), b)

_, b = req("POST", "/api/diagnose", {"capital": 50000, "dailyHours": 8, "city": "上海"},
           token=token, guest=GUEST)
task_id = data_of(b).get("taskId") or data_of(b).get("task_id")
check("准备：提交诊断", bool(task_id), b)

for _ in range(60):
    _, b = req("GET", f"/api/diagnose/{task_id}/progress", token=token, guest=GUEST)
    if data_of(b).get("status") in ("ready", "failed"):
        break
    time.sleep(0.4)

_, b = req("GET", f"/api/match?taskId={task_id}", token=token, guest=GUEST)
cards = data_of(b).get("free") or data_of(b).get("opportunities") or []
opp_id = cards[0].get("id") if cards else None
check("准备：商机匹配", bool(opp_id), b)

_, b = req("POST", "/api/payment/create", {"plan": "single", "platform": "web", "matchId": opp_id},
           token=token, guest=GUEST)
order_id = data_of(b).get("orderId") or data_of(b).get("order_id")
channel = data_of(b).get("channel") or "wechat"
check("准备：创建订单", bool(order_id), b)

_, b = req("POST", f"/api/payment/callback/{channel}", {"order_id": order_id, "result": "success"},
           guest=GUEST)
check("准备：支付成功", data_of(b).get("status") in ("paid", "generating", "delivered"), b)

# ───────── 1. 6 个并发 create ─────────
results: list[tuple[int, dict]] = []
lock = threading.Lock()
barrier = threading.Barrier(6)


def fire():
    barrier.wait()
    r = req("POST", "/api/package/create", {"orderId": order_id, "matchId": opp_id},
            token=token, guest=GUEST)
    with lock:
        results.append(r)


threads = [threading.Thread(target=fire) for _ in range(6)]
for t in threads:
    t.start()
for t in threads:
    t.join()

codes = [r[0] for r in results]
envelopes = [r[1].get("code") for r in results]
check("并发 create 全部 HTTP 200（无 500）", all(c == 200 for c in codes), codes)
check("并发 create 全部业务成功 code=0", all(c == 0 for c in envelopes), envelopes)

# ───────── 2. 并发轮询进度 ─────────
final = {}
statuses: list[str] = []
for _ in range(90):
    _, b = req("GET", f"/api/package/{order_id}/progress", token=token, guest=GUEST)
    final = data_of(b)
    statuses.append(b.get("code"))
    if final.get("status") in ("delivered", "failed"):
        break
    time.sleep(0.5)

check("进度接口全程 code=0（不再 50001）", all(c == 0 for c in statuses), statuses[-5:])
check("最终状态 delivered", final.get("status") == "delivered", final)
check("进度 done=10 / percent=100",
      final.get("done") == 10 and final.get("percent") == 100, final)

# ───────── 3. 数据库层面的唯一性 ─────────
rows = q("SELECT id FROM packages WHERE order_id = ?", (order_id,))
check("packages 表该订单恰好 1 行（不再重复）", len(rows) == 1, rows)

if rows:
    files = q("SELECT code, file_type FROM deliverable_files WHERE package_id = ?", (rows[0][0],))
    codes_set = sorted({c for c, _ in files})
    fmts_set = sorted({f for _, f in files})
    check("deliverable_files 恰好 15 行（10 件 / 多格式）", len(files) == 15, len(files))
    check("覆盖 D01–D10 十件交付物", codes_set == [f"D{i:02d}" for i in range(1, 11)], codes_set)
    check("覆盖 5 种格式 pdf/excel/word/png/svg",
          set(fmts_set) >= {"pdf", "excel", "word", "png", "svg"}, fmts_set)

# ───────── 4. 完成后重复 create 的幂等 ─────────
_, b = req("POST", "/api/package/create", {"orderId": order_id}, token=token, guest=GUEST)
check("交付后重复 create 幂等返回 delivered",
      b.get("code") == 0 and data_of(b).get("status") == "delivered", b)
time.sleep(2)
rows2 = q("SELECT id FROM packages WHERE order_id = ?", (order_id,))
check("重复 create 未新增 package 行", len(rows2) == len(rows), rows2)

_, b = req("GET", f"/api/package/{order_id}", token=token, guest=GUEST)
items = data_of(b).get("items") or []
check("详情返回 10 件交付物（含 formats 多格式）",
      len(items) == 10 and all(len(i.get("formats") or []) >= 1 for i in items), len(items))

print("-" * 78)
print(f"结果：PASS={PASS}  FAIL={FAIL}")
if FAILED:
    print("失败项：", FAILED)
print("=" * 78)
raise SystemExit(1 if FAIL else 0)
