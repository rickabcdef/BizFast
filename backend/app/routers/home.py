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
    """首屏点选式入口的档位配置。

    档位必须与前端 `pages/m1_home/index.tsx` 实际渲染的滑块完全一致
    （此前后端只给 2 档时间、前端却有 3 档，属于契约漂移；已对齐为 3 档）。
    """
    return ok(
        {
            # M1-01 启动资金四档（前端滑块 4 档）
            "capitals": [
                {"label": "1万以下", "value": 1},
                {"label": "1-5万", "value": 2},
                {"label": "5-20万", "value": 3},
                {"label": "20万以上", "value": 4},
            ],
            # M1-01 可投入时间三档（前端滑块 3 档）
            "dailyHours": [
                {"label": "兼职（每天约 2 小时）", "value": 2},
                {"label": "半天（每天约 4 小时）", "value": 4},
                {"label": "全职（每天 8 小时以上）", "value": 8},
            ],
            # 城市枚举版本号：前端按此判断是否需重新拉取城市列表
            # （settings 字段名是 city_list_version；此前写 city_version，getattr 恒取默认值）
            "cityVersion": getattr(settings, "city_list_version", "2026.1"),
        },
        _rid(request),
    )
