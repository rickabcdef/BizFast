"""首屏配置路由 - 负责人 D - 对应 m1_home (M1)

GET /api/home/config：返回资金/时间档位、城市枚举版本号（见 docs/api-contract.md M1）。
纯静态配置，无需登录（M1-07 游客可用）。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas.common import ok

router = APIRouter(prefix="/api", tags=["home"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("/home/config", summary="首屏配置（M1）")
async def home_config(request: Request):
    return ok(
        {
            # M1-03 启动资金四档
            "capitals": [
                {"label": "1万以下", "value": 1},
                {"label": "1–5万", "value": 2},
                {"label": "5–20万", "value": 3},
                {"label": "20万以上", "value": 4},
            ],
            # M1-04 每日时间两档
            "dailyHours": [
                {"label": "兼职（每天约2小时）", "value": 2},
                {"label": "全职（每天8小时以上）", "value": 8},
            ],
            # M1-05 城市枚举版本号：前端按此判断是否需重新拉取 300+ 城市列表
            "cityVersion": getattr(settings, "city_version", "2026.1"),
        },
        _rid(request),
    )
