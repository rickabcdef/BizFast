"""M7 解压小游戏路由

提供 2 款内置小游戏：
1. 消消乐 (match3) - 经典消除游戏
2. 2048 - 数字合并游戏

功能：
- 提交游戏分数
- 查询排行榜
- 查询个人分数历史
- 查询个人最高分

游客也能玩：先用 `ensure_owner_user` 落一条 role=guest 的用户行，
再用其 id 记分（GameScore.user_id 是外键，不能为空）。
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import OwnerContext, current_owner, ensure_owner_user
from app.core.database import get_db
from app.schemas.common import ok
from app.services import games as games_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/games", tags=["M7 解压小游戏"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.post("/score", summary="提交游戏分数")
async def submit_score(
    request: Request,
    game_type: Annotated[str, Body(description="游戏类型 (match3/2048)")],
    score: Annotated[int, Body(description="游戏得分", ge=0)],
    duration_seconds: Annotated[Optional[int], Body(description="游戏时长（秒）")] = None,
    extra_data: Annotated[Optional[dict], Body(description="额外数据")] = None,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """提交游戏分数。

    支持的游戏类型：
    - `match3`: 消消乐
    - `2048`: 数字合并

    返回排名和是否打破个人记录。
    """
    # 需要用户身份（游客或登录）——先保证存在对应的 User 行
    user = await ensure_owner_user(db, owner)

    result = await games_service.submit_score(
        db=db,
        user_id=user.id,
        game_type=game_type,
        score=score,
        duration_seconds=duration_seconds,
        extra_data=extra_data,
    )

    return ok(result, _rid(request))


@router.get("/leaderboard/{game_type}", summary="获取游戏排行榜")
async def get_leaderboard(
    game_type: str,
    request: Request,
    limit: Annotated[int, Query(description="返回数量", ge=1, le=100)] = 100,
    db: AsyncSession = Depends(get_db),
):
    """获取指定游戏的排行榜。

    排行榜基于每个玩家的最高分计算。
    """
    result = await games_service.get_leaderboard(
        db=db,
        game_type=game_type,
        limit=limit,
    )

    return ok(result, _rid(request))


@router.get("/my-scores", summary="获取我的分数历史")
async def get_my_scores(
    request: Request,
    game_type: Annotated[Optional[str], Query(description="游戏类型（可选）")] = None,
    limit: Annotated[int, Query(description="返回数量", ge=1, le=50)] = 10,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的游戏分数历史。

    可指定游戏类型筛选，不传则返回所有游戏的分数。
    """
    user = await ensure_owner_user(db, owner)

    result = await games_service.get_user_scores(
        db=db,
        user_id=user.id,
        game_type=game_type,
        limit=limit,
    )

    return ok(result, _rid(request))


@router.get("/my-best/{game_type}", summary="获取我的个人最高分")
async def get_my_best(
    game_type: str,
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """获取指定游戏中当前用户的最高分和排名。"""
    user = await ensure_owner_user(db, owner)

    result = await games_service.get_personal_best(
        db=db,
        user_id=user.id,
        game_type=game_type,
    )

    return ok(result, _rid(request))
