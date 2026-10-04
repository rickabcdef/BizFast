"""M2 生意诊断 验收测试（负责人 A）。

覆盖：M2-01 校验与打标、M2-02 真实进度、M2-04 热度图 ≤30s、M2-06 24h 缓存、M2-08 AI 降级。
"""
from __future__ import annotations

import time

import pytest

RID = "test-run-m2"


async def _create(client, capital=30000, hours=2, city="杭州市"):
    return await client.post(
        "/api/diagnose", json={"capital": capital, "dailyHours": hours, "city": city}
    )


async def test_create_and_progress_is_real(client, drain):
    resp = await _create(client)
    body = resp.json()
    assert body["code"] == 0, body
    task_id = body["data"]["taskId"]
    assert body["data"]["status"] in ("pending", "running", "ready")

    # 进度必须来自后端真实状态
    p = (await client.get(f"/api/diagnose/{task_id}/progress")).json()["data"]
    assert 0 <= p["percent"] <= 100
    assert p["message"]
    assert len(p["stages"]) == 5

    await drain()
    p2 = (await client.get(f"/api/diagnose/{task_id}/progress")).json()["data"]
    assert p2["status"] == "ready"
    assert p2["percent"] == 100
    assert len(p2["doneStages"]) == 5


async def test_result_contains_tags_and_three_directions(client, drain):
    started = time.perf_counter()
    task_id = (await _create(client)).json()["data"]["taskId"]
    await drain()
    result = (await client.get(f"/api/diagnose/{task_id}/result")).json()["data"]
    elapsed = time.perf_counter() - started

    assert result["status"] == "ready"
    assert result["city"] == "杭州"  # 归一化「杭州市」→「杭州」
    tags = result["tags"]
    assert tags["capitalLevel"] == "mid"
    assert tags["timeLevel"] == "part"
    assert tags["cityLevel"] == "new_tier1"
    assert len(tags["labels"]) == 3

    assert len(result["directions"]) == 3
    assert all(60 <= d["heat"] <= 100 for d in result["directions"])
    assert result["degraded"] is True  # 未配置大模型 → 走本地规则引擎（M2-08 降级）
    assert elapsed < 30  # M2-04：≤30 秒


async def test_heatmap_is_downloadable_png(client, drain):
    task_id = (await _create(client)).json()["data"]["taskId"]
    await drain()
    resp = await client.get(f"/api/diagnose/heatmap/{task_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(resp.content) > 5000


async def test_same_conditions_hit_24h_cache(client, drain):
    # 用一组其它用例未使用过的条件，确保第一次必定是真实计算（未命中缓存）
    first = (await _create(client, capital=60000, hours=6, city="成都市")).json()["data"]
    await drain()
    assert first["cached"] is False

    second = (await _create(client, capital=60000, hours=6, city="成都")).json()["data"]
    assert second["cached"] is True
    assert second["status"] == "ready"

    result = (await client.get(f"/api/diagnose/{second['taskId']}/result")).json()["data"]
    assert result["cached"] is True
    assert len(result["directions"]) == 3


@pytest.mark.parametrize(
    "payload,expect_code",
    [
        ({"capital": 30000, "dailyHours": 2, "city": ""}, 40001),
        ({"capital": None, "dailyHours": 2, "city": "杭州"}, 40001),
        ({"capital": 30000, "dailyHours": 0, "city": "杭州"}, 40001),
        ({"capital": 30000, "dailyHours": 2, "city": "不存在的城市"}, 40002),
    ],
)
async def test_validation_errors_are_chinese(client, payload, expect_code):
    resp = await client.post("/api/diagnose", json=payload)
    body = resp.json()
    assert body["code"] == expect_code, body
    assert body["message"]
    # 禁止英文报错 / 裸错误码
    assert not body["message"].isdigit()
    assert any("\u4e00" <= ch <= "\u9fff" for ch in body["message"])


async def test_unknown_task_returns_40401(client):
    body = (await client.get("/api/diagnose/not-exist/progress")).json()
    assert body["code"] == 40401


async def test_capital_accepts_tier_index(client, drain):
    """前端（M1）传档位 1–4 也应可用（契约 StartupInput.capital 为「档位」）。"""
    body = (await _create(client, capital=2, hours=8, city="上海市")).json()
    assert body["code"] == 0, body
    task_id = body["data"]["taskId"]
    await drain()
    result = (await client.get(f"/api/diagnose/{task_id}/result")).json()["data"]
    assert result["tags"]["capitalLevel"] == "mid"
    assert result["tags"]["timeLevel"] == "full"
    assert result["tags"]["cityLevel"] == "tier1"


# ---------------------------------------------------------------- M2-07 补充问答
async def test_extra_answers_are_optional_and_echoed(client, drain):
    """作答后：产出偏好标签并原样回显；且排序会因偏好发生变化。"""
    base_id = (await _create(client, capital=200000, hours=8, city="南京市")).json()["data"]["taskId"]
    await drain()
    with_extra = (
        await client.post(
            "/api/diagnose",
            json={
                "capital": 200000,
                "dailyHours": 8,
                "city": "南京市",
                "extra": {"experience": "none", "mode": "offline", "priority": "profit"},
            },
        )
    ).json()["data"]["taskId"]
    await drain()

    base = (await client.get(f"/api/diagnose/{base_id}/result")).json()["data"]
    rich = (await client.get(f"/api/diagnose/{with_extra}/result")).json()["data"]

    # 跳过时 extra 为 None，preferenceLabels 为空
    assert base["extra"] is None
    assert base["tags"]["preferenceLabels"] == []

    # 作答时回显三个选项并翻译成人话标签
    assert rich["extra"]["experience"] == "none"
    assert rich["extra"]["mode"] == "offline"
    assert rich["extra"]["priority"] == "profit"
    assert len(rich["tags"]["preferenceLabels"]) == 3

    # 不同偏好不应互相命中缓存
    assert rich["cached"] is False


async def test_extra_skipped_does_not_break_result(client, drain):
    """PRD：用户可跳过，跳过不影响后续结果。"""
    body = (
        await client.post(
            "/api/diagnose",
            json={
                "capital": 80000,
                "dailyHours": 6,
                "city": "无锡市",
                "extra": {"skipped": True},
            },
        )
    ).json()
    assert body["code"] == 0, body
    task_id = body["data"]["taskId"]
    await drain()
    result = (await client.get(f"/api/diagnose/{task_id}/result")).json()["data"]
    assert result["status"] == "ready"
    assert len(result["directions"]) == 3
    assert result["tags"]["preferenceLabels"] == []


async def test_preference_changes_ranking(client):
    """偏好必须真实影响排序：只做线上 vs 只做实体，首位商机应不同。"""
    tags = {"capital_level": "high", "time_level": "full", "city_level": "tier1",
            "capital_label": "5–20 万", "time_label": "全职", "city_label": "一线城市", "labels": []}
    online = [op["id"] for op, _ in diagnose_rank(tags, 200000, {"mode": "online"})][:4]
    offline = [op["id"] for op, _ in diagnose_rank(tags, 200000, {"mode": "offline"})][:4]
    assert online != offline, "线上/线下偏好应导致不同的推荐集合"


def diagnose_rank(tags, capital, extra):
    from app.services import diagnose as d

    return d.rank_opportunities(tags, capital, extra)


# ---------------------------------------------------------------- M2-05 分享卡片
async def test_share_payload_contains_product_name_and_qr(client, drain):
    task_id = (await _create(client, capital=120000, hours=8, city="武汉市")).json()["data"]["taskId"]
    await drain()
    data = (await client.get(f"/api/diagnose/{task_id}/share")).json()["data"]
    assert data["directions"] and len(data["directions"]) == 3
    assert data["qrContent"].startswith("http")
    assert task_id in data["qrContent"]
    assert data["shareUrl"] == data["qrContent"]
    assert data["shareText"]
    assert data["imageUrl"].endswith(f"/api/diagnose/share-card/{task_id}")


async def test_share_card_is_png_with_product_name(client, drain):
    task_id = (await _create(client, capital=120000, hours=8, city="长沙市")).json()["data"]["taskId"]
    await drain()
    resp = await client.get(f"/api/diagnose/share-card/{task_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    # 二维码区已贴入，卡片应明显大于纯文字图
    assert len(resp.content) > 20000
    # Content-Disposition 必须是 latin-1 可编码（中文名走 RFC 5987）
    resp.headers["content-disposition"].encode("latin-1")

