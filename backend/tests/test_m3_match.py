"""M3 商机匹配 验收测试（负责人 A）。

覆盖：M3-01 三个强相关商机、M3-02 五要素数字卡、M3-03 详情、M3-04 真实案例、
M3-05 风险≥3+止损、M3-06 收藏、M3-07 第 4 个锁定商机付费拦截。
"""
from __future__ import annotations

import pytest

CONDITIONS = {"capital": 30000, "dailyHours": 2, "city": "杭州市"}


async def _task(client, drain, **overrides):
    payload = {**CONDITIONS, **overrides}
    task_id = (await client.post("/api/diagnose", json=payload)).json()["data"]["taskId"]
    await drain()
    return task_id


async def test_three_free_cards_plus_locked(client, drain):
    task_id = await _task(client, drain)
    body = (await client.get("/api/match", params={"taskId": task_id})).json()
    assert body["code"] == 0, body
    data = body["data"]

    assert len(data["free"]) == 3
    assert data["locked"]["locked"] is True
    assert data["totalCandidates"] >= 4

    ids = [o["id"] for o in data["free"]] + [data["locked"]["id"]]
    assert len(set(ids)) == 4

    # 推荐指数按分数倒序（锁定卡为最佳匹配）
    scores = [o["recommendScore"] for o in data["free"]]
    assert scores == sorted(scores, reverse=True)
    assert data["locked"]["recommendScore"] >= scores[0]

    for card in data["free"]:
        five = card["fiveElements"]
        assert five["capital"] and five["payback"] and five["margin"]
        assert five["firstCustomer"] and five["difficulty"]
        # M3-02：说人话，不出现专业术语
        assert "万元" in five["capital"] or "元" in five["capital"]
        assert five["payback"].endswith("个月")
        assert five["margin"].endswith("%")
        assert len(card["risks"]) >= 3
        assert card["metrics"]["recommendScore"] == card["recommendScore"]


async def test_free_detail_has_full_content(client, drain):
    task_id = await _task(client, drain)
    free = (
        await client.get("/api/match", params={"taskId": task_id})
    ).json()["data"]["free"]
    oid = free[0]["id"]

    body = (await client.get(f"/api/match/{oid}", params={"taskId": task_id})).json()
    assert body["code"] == 0, body
    d = body["data"]
    assert d["locked"] is False
    assert len(d["cases"]) >= 2
    for case in d["cases"]:
        assert case["source"] and case["time"] and case["highlight"]
    assert len(d["risks"]) >= 3
    assert d["stopLoss"]
    assert d["costBreakdown"] and d["revenueEstimate"]
    assert d["intro"] and d["targetCustomers"] and d["steps"]


async def test_locked_detail_requires_entitlement(client, drain):
    task_id = await _task(client, drain)
    locked_id = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]["locked"]["id"]

    body = (await client.get(f"/api/match/{locked_id}", params={"taskId": task_id})).json()
    assert body["code"] == 40301, body
    assert "付费" in body["message"]

    entitled = (
        await client.get(f"/api/match/{locked_id}/entitled")
    ).json()["data"]["entitled"]
    assert entitled is False


async def test_match_list_is_related_to_conditions(client, drain):
    """不同资金档位应得到不同的匹配结果（不是通用推荐）。"""
    low = await _task(client, drain, capital=5000, hours=2, city="成都市")
    high = await _task(client, drain, capital=350000, hours=8, city="上海市")

    low_ids = [o["id"] for o in (await client.get("/api/match", params={"taskId": low})).json()["data"]["free"]]
    high_ids = [o["id"] for o in (await client.get("/api/match", params={"taskId": high})).json()["data"]["free"]]
    assert low_ids != high_ids


async def test_favorite_toggle(client, drain):
    task_id = await _task(client, drain)
    oid = (await client.get("/api/match", params={"taskId": task_id})).json()["data"]["free"][0]["id"]

    first = (await client.post(f"/api/match/{oid}/favorite")).json()["data"]
    assert first["favorited"] is True
    second = (await client.post(f"/api/match/{oid}/favorite")).json()["data"]
    assert second["favorited"] is False


async def test_unknown_opportunity(client):
    body = (await client.get("/api/match/not-a-real-id")).json()
    assert body["code"] == 40401
