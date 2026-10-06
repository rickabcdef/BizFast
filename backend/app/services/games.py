"""M7 解压小游戏服务

提供 2 款内置小游戏：
1. 消消乐 - 经典消除游戏
2. 2048 - 数字合并游戏

功能：
- 记录玩家分数和排名
- 支持游客和登录用户
- 分数持久化存储
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError
from app.models import GameScore

logger = logging.getLogger(__name__)

# 游戏类型
GAME_TYPES = {
    "match3": "消消乐",
    "2048": "2048",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def submit_score(
    db: AsyncSession,
    user_id: str,
    game_type: str,
    score: int,
    duration_seconds: Optional[int] = None,
    extra_data: Optional[dict] = None,
) -> dict:
    """提交游戏分数。

    Args:
        user_id: 用户 ID
        game_type: 游戏类型 (match3/2048)
        score: 游戏得分
        duration_seconds: 游戏时长（秒）
        extra_data: 额外数据（如关卡数、最大合并数字等）

    Returns:
        {
            "score_id": "...",
            "score": 12345,
            "rank": 10,
            "is_personal_best": True
        }
    """
    if game_type not in GAME_TYPES:
        raise BizError(40001, f"未知的游戏类型: {game_type}")

    if score < 0:
        raise BizError(40001, "分数不能为负数")

    # 检查是否打破个人记录
    existing_best = await db.execute(
        select(GameScore)
        .where(
            GameScore.user_id == user_id,
            GameScore.game_type == game_type,
        )
        .order_by(desc(GameScore.score))
        .limit(1)
    )
    best_record = existing_best.scalar_one_or_none()
    is_personal_best = best_record is None or score > best_record.score

    # 创建分数记录
    score_record = GameScore(
        id=str(uuid.uuid4()),
        user_id=user_id,
        game_type=game_type,
        score=score,
        duration_seconds=duration_seconds,
        extra_data=extra_data,
        is_personal_best=is_personal_best,
        created_at=_now(),
    )
    db.add(score_record)

    # 如果打破个人记录，更新其他记录的 is_personal_best
    if is_personal_best and best_record:
        old_records = await db.execute(
            select(GameScore).where(
                GameScore.user_id == user_id,
                GameScore.game_type == game_type,
                GameScore.is_personal_best == True,
            )
        )
        for record in old_records.scalars().all():
            record.is_personal_best = False
        score_record.is_personal_best = True

    await db.commit()
    await db.refresh(score_record)

    # 计算排名
    rank_result = await db.execute(
        select(GameScore)
        .where(
            GameScore.game_type == game_type,
            GameScore.score > score,
        )
    )
    rank = len(rank_result.scalars().all()) + 1

    logger.info(
        f"游戏分数提交: user_id={user_id}, game={game_type}, "
        f"score={score}, rank={rank}, is_best={is_personal_best}"
    )

    return {
        "score_id": score_record.id,
        "score": score,
        "rank": rank,
        "is_personal_best": is_personal_best,
    }


async def get_leaderboard(
    db: AsyncSession,
    game_type: str,
    limit: int = 100,
) -> dict:
    """获取游戏排行榜。

    Args:
        game_type: 游戏类型
        limit: 返回数量（最大 100）

    Returns:
        {
            "game_type": "2048",
            "game_name": "2048",
            "total_players": 1234,
            "leaderboard": [
                {
                    "rank": 1,
                    "user_id": "...",
                    "username": "用户A",
                    "score": 99999,
                    "duration_seconds": 300,
                    "created_at": "..."
                },
                ...
            ]
        }
    """
    if game_type not in GAME_TYPES:
        raise BizError(40001, f"未知的游戏类型: {game_type}")

    limit = min(max(limit, 1), 100)

    # 查询最高分（每个用户只取最高分）
    # 使用子查询获取每个用户的最高分
    from sqlalchemy import func

    subquery = (
        select(
            GameScore.user_id,
            func.max(GameScore.score).label("max_score"),
        )
        .where(GameScore.game_type == game_type)
        .group_by(GameScore.user_id)
        .subquery()
    )

    # 关联查询完整记录
    result = await db.execute(
        select(GameScore)
        .join(
            subquery,
            (GameScore.user_id == subquery.c.user_id)
            & (GameScore.score == subquery.c.max_score),
        )
        .where(GameScore.game_type == game_type)
        .order_by(desc(GameScore.score))
        .limit(limit)
    )
    records = list(result.scalars().all())

    # 构建排行榜
    leaderboard = []
    for rank, record in enumerate(records, start=1):
        # 获取用户名（简化处理，实际应关联 User 表）
        username = f"玩家{record.user_id[:8]}"

        leaderboard.append({
            "rank": rank,
            "user_id": record.user_id,
            "username": username,
            "score": record.score,
            "duration_seconds": record.duration_seconds,
            "created_at": record.created_at.isoformat(),
        })

    # 查询总玩家数
    total_result = await db.execute(
        select(func.count(func.distinct(GameScore.user_id)))
        .where(GameScore.game_type == game_type)
    )
    total_players = total_result.scalar() or 0

    return {
        "game_type": game_type,
        "game_name": GAME_TYPES[game_type],
        "total_players": total_players,
        "leaderboard": leaderboard,
    }


async def get_user_scores(
    db: AsyncSession,
    user_id: str,
    game_type: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """获取用户的游戏分数历史。

    Args:
        user_id: 用户 ID
        game_type: 游戏类型（可选，不传则返回所有游戏）
        limit: 返回数量

    Returns:
        {
            "scores": [
                {
                    "game_type": "2048",
                    "game_name": "2048",
                    "score": 12345,
                    "rank": 10,
                    "is_personal_best": True,
                    "duration_seconds": 300,
                    "created_at": "..."
                },
                ...
            ]
        }
    """
    query = select(GameScore).where(GameScore.user_id == user_id)

    if game_type:
        if game_type not in GAME_TYPES:
            raise BizError(40001, f"未知的游戏类型: {game_type}")
        query = query.where(GameScore.game_type == game_type)

    query = query.order_by(desc(GameScore.created_at)).limit(limit)

    result = await db.execute(query)
    records = list(result.scalars().all())

    scores = []
    for record in records:
        # 计算排名
        rank_result = await db.execute(
            select(GameScore)
            .where(
                GameScore.game_type == record.game_type,
                GameScore.score > record.score,
            )
        )
        rank = len(rank_result.scalars().all()) + 1

        scores.append({
            "game_type": record.game_type,
            "game_name": GAME_TYPES.get(record.game_type, record.game_type),
            "score": record.score,
            "rank": rank,
            "is_personal_best": record.is_personal_best,
            "duration_seconds": record.duration_seconds,
            "extra_data": record.extra_data,
            "created_at": record.created_at.isoformat(),
        })

    return {
        "scores": scores,
    }


async def get_personal_best(
    db: AsyncSession,
    user_id: str,
    game_type: str,
) -> dict:
    """获取用户个人最高分。

    Args:
        user_id: 用户 ID
        game_type: 游戏类型

    Returns:
        {
            "game_type": "2048",
            "game_name": "2048",
            "best_score": 12345,
            "best_rank": 10,
            "total_games": 50,
            "best_game": {
                "score_id": "...",
                "score": 12345,
                "duration_seconds": 300,
                "created_at": "..."
            }
        }
    """
    if game_type not in GAME_TYPES:
        raise BizError(40001, f"未知的游戏类型: {game_type}")

    # 查询最高分
    result = await db.execute(
        select(GameScore)
        .where(
            GameScore.user_id == user_id,
            GameScore.game_type == game_type,
        )
        .order_by(desc(GameScore.score))
        .limit(1)
    )
    best_record = result.scalar_one_or_none()

    if not best_record:
        return {
            "game_type": game_type,
            "game_name": GAME_TYPES[game_type],
            "best_score": 0,
            "best_rank": 0,
            "total_games": 0,
            "best_game": None,
        }

    # 查询总游戏次数
    from sqlalchemy import func

    total_result = await db.execute(
        select(func.count(GameScore.id))
        .where(
            GameScore.user_id == user_id,
            GameScore.game_type == game_type,
        )
    )
    total_games = total_result.scalar() or 0

    # 计算排名
    rank_result = await db.execute(
        select(GameScore)
        .where(
            GameScore.game_type == game_type,
            GameScore.score > best_record.score,
        )
    )
    best_rank = len(rank_result.scalars().all()) + 1

    return {
        "game_type": game_type,
        "game_name": GAME_TYPES[game_type],
        "best_score": best_record.score,
        "best_rank": best_rank,
        "total_games": total_games,
        "best_game": {
            "score_id": best_record.id,
            "score": best_record.score,
            "duration_seconds": best_record.duration_seconds,
            "extra_data": best_record.extra_data,
            "created_at": best_record.created_at.isoformat(),
        },
    }
