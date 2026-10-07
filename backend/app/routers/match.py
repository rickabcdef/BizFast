"""商机匹配 - 负责人 A - 对应 m3_match

路由前缀: /api/match
契约: docs/api-contract.md「M3 商机匹配」
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_owner
from app.core.database import get_db
from app.schemas.common import ok
from app.services import diagnose as diagnose_service
from app.services import match as match_service

router = APIRouter(prefix="/api/match", tags=["match"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("", summary="按诊断结果返回 3 个免费商机 + 第 4 个锁定商机")
async def list_match(
    request: Request,
    task_id: str = Query(..., alias="taskId"),
    db: AsyncSession = Depends(get_db),
):
    task = await diagnose_service.get_task(db, task_id)
    return ok(await match_service.get_match_list(db, task), _rid(request))


@router.get("/favorites", summary="我的收藏商机（V5.0 M10）")
async def list_favorites(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await match_service.list_favorites(db, owner), _rid(request))


@router.get("/{opportunity_id}", summary="商机详情（锁定商机需已解锁，否则 40301）")
async def match_detail(
    opportunity_id: str,
    request: Request,
    task_id: str | None = Query(None, alias="taskId"),
    db: AsyncSession = Depends(get_db),
):
    owner = current_owner(request)
    detail = await match_service.get_detail(db, owner, opportunity_id, task_id)
    return ok(detail, _rid(request))


@router.post("/{opportunity_id}/favorite", summary="收藏 / 取消收藏商机（M3-06）")
async def favorite(
    opportunity_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    result = await match_service.toggle_favorite(db, owner, opportunity_id)
    return ok(result, _rid(request))


@router.get("/{opportunity_id}/entitled", summary="当前用户是否已解锁该商机的完整方案")
async def entitled(
    opportunity_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    return ok(
        {"opportunity_id": opportunity_id, "entitled": await match_service.is_entitled(db, owner, opportunity_id)},
        _rid(request),
    )
