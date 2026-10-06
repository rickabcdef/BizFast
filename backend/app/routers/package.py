"""M4 启动包生成路由

路由前缀: /api/package（另有 /api/packages 列表路由）
对应前端: m4_delivery

付费成功后，异步生成 D01–D10 十件交付物（含多格式），前端轮询真实进度，
全部完成后打包 ZIP，支持单文件下载/预览与整体下载。

契约见 docs/api-contract.md M4 章节：
- POST /api/package/create                body:{orderId?, matchId?} → {orderId}
- GET  /api/package/{orderId}/progress    → {stage, percent, done, total, currentItem, retryCount, status}
- GET  /api/package/{orderId}             → {items:[{code,name,fileType,url,formats[]}], zipUrl, status, retryCount}
- GET  /api/package/{orderId}/item/{code}?format=  单件下载/预览
- GET  /api/package/{orderId}/zip         打包 ZIP 下载（包内中文命名）
- POST /api/package/{orderId}/regenerate
- GET  /api/packages                      我的启动包列表（按时间倒序）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import OwnerContext, current_owner, ensure_owner_user
from app.core.database import get_db
from app.core.errors import BizError
from app.models import DeliverableFile, Order, Package
from app.office import DELIVERABLES, DELIVERABLE_FORMATS
from app.schemas.common import ok
from app.storage import get_storage, url_to_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/package", tags=["M4 启动包生成"])
# 列表路由不带 /package 前缀（契约：GET /api/packages）
list_router = APIRouter(prefix="/api", tags=["M4 启动包生成"])

# 交付物 MIME（预览要正确渲染 PDF / 图片，必须给准 Content-Type）
_MIME = {
    "pdf": "application/pdf",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
    "svg": "image/svg+xml",
    "txt": "text/plain; charset=utf-8",
    "zip": "application/zip",
}
_EXT = {"pdf": "pdf", "excel": "xlsx", "word": "docx", "png": "png", "svg": "svg", "txt": "txt", "zip": "zip"}

_STATUS_LABEL = {
    "generating": "生成中",
    "delivered": "已交付",
    "failed": "生成失败",
}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
#  组装 / 查询辅助
# ──────────────────────────────────────────────
async def _get_package(db: AsyncSession, order_id: str) -> Package | None:
    """取订单对应的启动包（一个订单一个包）。

    用 `.first()` 而不是 `scalar_one_or_none()`：唯一约束生效前产生的历史重复行
    不该把接口打成 500（MultipleResultsFound），这里容错取最早的一条。
    """
    return (await db.execute(
        select(Package).where(Package.order_id == order_id).order_by(Package.created_at.asc())
    )).scalars().first()


async def _get_items(db: AsyncSession, package_id: str) -> list[DeliverableFile]:
    result = await db.execute(
        select(DeliverableFile).where(DeliverableFile.package_id == package_id)
    )
    return list(result.scalars().all())


def _group_items(rows: list[DeliverableFile]) -> list[dict]:
    """把「一件交付物一个格式一行」的数据按 code 聚合成含 formats 的前端结构。

    formats 顺序严格按 PRD 4.4.1 定义（主格式排第一），未生成的格式不出现在列表里。
    """
    by_code: dict[str, dict[str, DeliverableFile]] = {}
    for row in rows:
        by_code.setdefault(row.code, {})[row.file_type] = row

    items: list[dict] = []
    for code in sorted(DELIVERABLES.keys()):
        name, primary = DELIVERABLES[code]
        formats_raw = by_code.get(code) or {}
        formats = []
        for fmt in DELIVERABLE_FORMATS.get(code, [primary]):
            row = formats_raw.get(fmt)
            if row is not None:
                formats.append({"file_type": fmt, "url": row.url})
        if not formats:
            continue  # 尚未生成该件（生成中/失败场景）
        items.append({
            "code": code,
            "name": name,
            "file_type": formats[0]["file_type"],
            "url": formats[0]["url"],
            "formats": formats,
            "status": "done",
        })
    return items


async def _package_payload(db: AsyncSession, pkg: Package) -> dict:
    items = _group_items(await _get_items(db, pkg.id))
    return {
        "order_id": pkg.order_id,
        "status": pkg.status,
        "items": items,
        "zip_url": f"/api/package/{pkg.order_id}/zip",
        "retry_count": pkg.retry_count or 0,
        "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
        "delivered_at": pkg.created_at.isoformat() if pkg.status == "delivered" else None,
    }


def _file_response(data: bytes, file_type: str, filename: str, ascii_name: str, inline: bool = True) -> Response:
    """直出文件字节：中文名走 RFC 5987（filename*），ASCII 兜底名给老浏览器。

    inline 让 PDF / 图片可在新标签页直接预览（M4-04 预览不产生额外费用），
    下载动作由前端 `<a download>` 决定（同源下优先级高于 Content-Disposition）。
    """
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{ascii_name}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        ),
        "Cache-Control": "private, max-age=300",
    }
    return Response(
        content=data,
        media_type=_MIME.get(file_type, "application/octet-stream"),
        headers=headers,
    )


# ──────────────────────────────────────────────
#  生成
# ──────────────────────────────────────────────
@router.post("/create", summary="创建启动包生成任务")
@router.post("/generate", include_in_schema=False, summary="（兼容别名）创建启动包生成任务")
async def create_package(
    request: Request,
    body: dict,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """付费成功后触发启动包生成（幂等）。

    请求体: { "orderId": "...", "matchId": "..."(可选) }
    返回 orderId，前端轮询 /progress 接口。
    """
    order_id = body.get("orderId") or body.get("order_id")
    if not order_id:
        raise BizError(code=40001, message="缺少订单 ID")

    # 确保有用户身份（游客先落库为用户行）
    user = await ensure_owner_user(db, owner)

    order = await db.get(Order, order_id)
    if not order:
        raise BizError(code=40401, message="未找到对应的订单")
    if order.user_id != user.id:
        raise BizError(code=40301, message="无权操作该订单")

    # 只有已支付（或已进入生成/交付）的订单才能生成启动包
    if order.status not in ("paid", "generating", "delivered"):
        raise BizError(code=60001, message="支付未成功，请重新支付")

    existing = await _get_package(db, order_id)
    if existing is not None and existing.status in ("generating", "delivered"):
        # 幂等：已生成/生成中直接返回当前状态，前端继续轮询即可（不在前端重复点击时二次入队）
        return ok({
            "order_id": order_id,
            "package_id": existing.id,
            "status": existing.status,
            "message": "启动包已交付" if existing.status == "delivered" else "启动包正在生成中",
        }, _rid(request))

    # 启动异步生成（inline 模式进程内调度；生产环境走 RQ）
    # force=False：并发/重复请求由 services.package 的「同订单生成锁 + 已交付短路」兜底，
    # 避免两次触发把 10 件交付物做两遍。
    from app.queue.runner import enqueue_background

    enqueue_background(
        lambda *a, **kw: _run_generation(order_id, user.id, force=False),
        rq_func="app.queue.worker.run_package",
        order_id=order_id,
        force=False,
    )

    return ok({
        "order_id": order_id,
        "package_id": existing.id if existing else None,  # 异步创建，稍后通过 progress 获取
        "status": "generating",
        "message": "启动包生成已启动，请轮询进度",
    }, _rid(request))


async def _run_generation(order_id: str, user_id: str, force: bool = False) -> None:
    """后台异步生成启动包（inline 模式由 runner 调度，生产由 RQ 消费）。

    实现统一收敛在 services/package.run_generation，此处只做转发，
    保证 HTTP 触发与队列触发走同一份逻辑（M4-01）。
    """
    from app.services import package as package_service

    await package_service.run_generation(order_id, user_id, force=force)


# ──────────────────────────────────────────────
#  进度
# ──────────────────────────────────────────────
@router.get("/{order_id}/progress", summary="轮询生成进度")
async def progress(
    order_id: str,
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """前端轮询此接口获取 D01-D10 的真实生成进度（M4-02：不造假）。

    返回：{status, total, done, percent, stage, message, currentItem, retryCount, items}
    """
    pkg = await _get_package(db, order_id)

    if not pkg:
        return ok({
            "order_id": order_id,
            "status": "generating",
            "total": 10,
            "done": 0,
            "percent": 0,
            "stage": "正在排队生成",
            "message": "已收到请求，AI 马上开工",
            "current_item": None,
            "retry_count": 0,
            "failed": False,
            "fail_reason": None,
            "items": [],
        }, _rid(request))

    rows = await _get_items(db, pkg.id)
    done_codes = {r.code for r in rows}
    done_count = len(done_codes)
    all_codes = sorted(DELIVERABLES.keys())

    retry_count = pkg.retry_count or 0
    failed = pkg.status == "failed"

    # 当前正在生成的文件名（第一个还没出的）
    current_item = None
    for code in all_codes:
        if code not in done_codes:
            current_item = DELIVERABLES[code][0]
            break

    if failed:
        stage = "AI 服务暂时不可用"
        message = "生成失败，正在自动重试（第 2/2 次）"
        fail_reason = "AI 服务暂时不可用，系统已自动重试 2 次仍未成功，我们将全额退款并第一时间通知你"
    elif done_count >= 10:
        stage = "10 件交付物已全部生成"
        message = "生成完成，正在打包 ZIP"
        fail_reason = None
    else:
        code_now = next((c for c in all_codes if c not in done_codes), None)
        stage = f"正在生成 {code_now} {DELIVERABLES[code_now][0]}" if code_now else "正在生成"
        message = f"已完成 {done_count}/10，AI 正在干活，别走开"
        fail_reason = None

    item_list = []
    for code in all_codes:
        name, _primary = DELIVERABLES[code]
        row = next((r for r in rows if r.code == code), None)
        item_list.append({
            "code": code,
            "name": name,
            "file_type": row.file_type if row else DELIVERABLES[code][1],
            "url": row.url if row else "",
            "status": "done" if row else "pending",
        })

    return ok({
        "order_id": order_id,
        "status": pkg.status,
        "total": 10,
        "done": done_count,
        "percent": done_count * 10,
        "stage": stage,
        "message": message,
        "current_item": current_item,
        "retry_count": retry_count,
        "failed": failed,
        "fail_reason": fail_reason,
        "items": item_list,
    }, _rid(request))


# ──────────────────────────────────────────────
#  详情 / 下载 / 预览
# ──────────────────────────────────────────────
@router.get("/{order_id}", summary="获取完整启动包")
async def get_package(
    order_id: str,
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """获取已交付的完整启动包（含所有交付物元数据、多格式与 ZIP 地址）。"""
    pkg = await _get_package(db, order_id)
    if not pkg:
        raise BizError(code=40401, message="未找到对应的生意启动包")

    payload = await _package_payload(db, pkg)
    if not payload["items"]:
        raise BizError(code=40401, message="未找到对应的生意启动包")
    return ok(payload, _rid(request))


@router.get("/{order_id}/item/{code}", summary="单件下载/预览")
async def download_item(
    order_id: str,
    code: str,
    request: Request,
    format: str | None = None,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """下载或预览单个交付物（M4-04，预览不产生额外费用）。

    `format` 缺省返回主格式，可选 pdf|excel|word|png|svg|txt。
    """
    pkg = await _get_package(db, order_id)
    if not pkg:
        raise BizError(code=40401, message="未找到对应的生意启动包")

    if code not in DELIVERABLES:
        raise BizError(code=40401, message="未找到对应的交付物")

    name, primary = DELIVERABLES[code]
    fmt = format or primary
    if fmt not in DELIVERABLE_FORMATS.get(code, [primary]):
        fmt = primary

    row = (await db.execute(
        select(DeliverableFile).where(
            DeliverableFile.package_id == pkg.id,
            DeliverableFile.code == code,
            DeliverableFile.file_type == fmt,
        )
    )).scalars().first()

    if row is None:
        raise BizError(code=40401, message=f"交付物 {code}（{fmt}）尚未生成")

    key = url_to_key(row.url)
    storage = get_storage()
    try:
        data = storage.read_bytes(key) if key else None
    except Exception as exc:
        logger.warning("读取交付物失败: %s key=%s - %s", code, key, exc)
        data = None

    if data is None:
        # 对象存储场景（或 key 无法反解）：回落到直链
        from fastapi.responses import RedirectResponse

        return RedirectResponse(row.url)

    ext = _EXT.get(fmt, "bin")
    filename = f"生意快启_{name}.{ext}"
    ascii_name = f"bizfast_{code}.{ext}"
    return _file_response(data, fmt, filename, ascii_name, inline=True)


@router.get("/{order_id}/zip", summary="ZIP 打包下载")
async def download_zip(
    order_id: str,
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """打包 ZIP 一键下载（M4-03：包内全部格式，中文命名）。"""
    pkg = await _get_package(db, order_id)
    if not pkg or not pkg.zip_url:
        raise BizError(code=40401, message="ZIP 文件尚未生成")

    key = url_to_key(pkg.zip_url)
    storage = get_storage()
    try:
        data = storage.read_bytes(key) if key else None
    except Exception as exc:
        logger.warning("读取 ZIP 失败: %s key=%s - %s", order_id, key, exc)
        data = None

    if data is None:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(pkg.zip_url)

    date_str = _now().strftime("%Y%m%d")
    filename = f"生意快启_完整启动包10件_{date_str}.zip"
    return _file_response(data, "zip", filename, "bizfast_package.zip", inline=False)


# ──────────────────────────────────────────────
#  重新生成
# ──────────────────────────────────────────────
@router.post("/{order_id}/regenerate", summary="重新生成启动包")
async def regenerate(
    order_id: str,
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """重新生成启动包（会员免费无限次 / 单次用户 1 次，M4-06）。"""
    user = await ensure_owner_user(db, owner)

    pkg = await _get_package(db, order_id)
    if not pkg:
        raise BizError(code=40401, message="未找到对应的生意启动包")
    if pkg.status != "delivered":
        raise BizError(code=40901, message="启动包尚未完成交付，无法重新生成")

    order = await db.get(Order, order_id)
    if order is None:
        raise BizError(code=40401, message="未找到对应的订单")

    if order.plan == "single" and (pkg.retry_count or 0) >= 1:
        raise BizError(code=40301, message="单次付费用户仅可重新生成 1 次，已用完")

    # 重置状态并启动重新生成（force：清掉旧交付物后重做）
    pkg.status = "generating"
    pkg.zip_url = None
    pkg.retry_count = (pkg.retry_count or 0) + 1
    order.status = "generating"
    order.generating_at = _now()
    await db.commit()

    from app.queue.runner import enqueue_background

    enqueue_background(
        lambda *a, **kw: _run_generation(order_id, user.id, force=True),
        rq_func="app.queue.worker.run_package",
        order_id=order_id,
        force=True,
    )

    remaining = None if order.plan != "single" else max(0, 1 - pkg.retry_count)
    return ok({
        "order_id": order_id,
        "status": "generating",
        "remaining": remaining,
        "message": "重新生成已启动",
    }, _rid(request))


# ──────────────────────────────────────────────
#  我的启动包列表（M4-05 / M10-01 共用）
# ──────────────────────────────────────────────
@list_router.get("/packages", summary="我的启动包列表")
async def my_packages(
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """云端永久保存的启动包列表，按创建时间倒序（M4-05）。"""
    user = await ensure_owner_user(db, owner)

    result = await db.execute(
        select(Package)
        .where(Package.user_id == user.id)
        .order_by(Package.created_at.desc())
    )
    pkgs = list(result.scalars().all())

    items = []
    for pkg in pkgs:
        payload = await _package_payload(db, pkg)
        if not payload["items"]:
            continue
        items.append(payload)

    return ok(items, _rid(request))
