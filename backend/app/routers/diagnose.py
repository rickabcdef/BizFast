"""生意诊断 - 负责人 A - 对应 m2_diagnose

路由前缀: /api/diagnose
契约: docs/api-contract.md「M2 诊断」
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.context import current_owner
from app.core.database import get_db
from app.schemas.common import ok
from app.schemas.diagnose import DiagnoseCreate
from app.services import diagnose as diagnose_service
from app.storage import get_storage

router = APIRouter(prefix="/api/diagnose", tags=["diagnose"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.post("", summary="提交三要素条件并创建诊断任务")
async def create_diagnose(
    payload: DiagnoseCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    owner = current_owner(request)
    task, cached = await diagnose_service.create_task(db, payload, owner)
    return ok(
        {"task_id": task.id, "cached": cached, "status": task.status, "percent": task.percent},
        _rid(request),
    )


@router.get("/{task_id}/progress", summary="诊断进度（真实阶段进度，不造假）")
async def diagnose_progress(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    task = await diagnose_service.get_task(db, task_id)
    return ok(diagnose_service.get_progress(task), _rid(request))


@router.get("/{task_id}/result", summary="诊断结果：标签 + 机会热度图")
async def diagnose_result(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    task = await diagnose_service.get_task(db, task_id)
    if task.status != "ready":
        return ok(
            {
                "task_id": task.id,
                "status": task.status,
                "city": task.city,
                "tags": None,
                "directions": [],
                "heatmap_url": "",
                "cached": task.cached,
                "degraded": task.degraded,
                "case_count": 0,
                "elapsed_ms": 0,
                "progress": diagnose_service.get_progress(task),
            },
            _rid(request),
        )
    return ok(diagnose_service.result_payload(task), _rid(request))


# ---------------------------------------------------------------- M2-05 分享
@router.get("/{task_id}/share", summary="分享卡片数据（产品名 + 二维码 + 3 个最热方向）")
async def diagnose_share(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    task = await diagnose_service.get_task(db, task_id)
    return ok(diagnose_service.share_card_payload(task, _share_url(request, task.id)), _rid(request))


@router.get("/share-card/{task_id}", summary="分享卡片图片（PNG，含产品名称与二维码）")
async def diagnose_share_card(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    task = await diagnose_service.get_task(db, task_id)
    png = diagnose_service.render_share_card_for_task(task, _share_url(request, task.id))
    filename = f"生意快启_机会热度图_{task.city}_分享卡.png"
    disposition = f"inline; filename=\"bizfast-share-card.png\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "public, max-age=86400",
        },
    )


def _share_url(request: Request, task_id: str) -> str:
    """分享落地页地址（二维码内容）。真实环境应由配置项指定正式域名。"""
    configured = getattr(settings, "share_base_url", "") or ""
    if configured:
        return f"{configured.rstrip('/')}/#/pages/m2_diagnose/index?taskId={task_id}"
    origin = f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"
    return f"{origin}/#/pages/m2_diagnose/index?taskId={task_id}"


@router.get("/heatmap/{task_id}", summary="机会热度图下载 / 预览（≤30 秒生成的第一份可带走成果）")
async def diagnose_heatmap(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await diagnose_service.get_task(db, task_id)
    if not task.heatmap_key:
        return Response(status_code=404, content="heatmap not ready")
    storage = get_storage()
    try:
        data = storage.read_bytes(task.heatmap_key)
    except Exception:
        return Response(status_code=404, content="heatmap not found")
    # HTTP 头必须是 latin-1 可编码：中文文件名只能用 RFC 5987 的 filename*=UTF-8'' 形式，
    # 同时保留一个 ASCII 兜底名，兼容老旧浏览器 / 下载器。
    filename = f"生意快启_机会热度图_{task.city}.png"
    disposition = f"inline; filename=\"opportunity-heatmap.png\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "public, max-age=86400",
        },
    )
