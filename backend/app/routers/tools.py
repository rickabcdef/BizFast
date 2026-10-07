"""M6 工具箱路由

提供 4 个实用工具：
1. 图片压缩与格式转换 - POST /api/tools/image/compress
2. PDF 合并 - POST /api/tools/pdf/merge
3. PDF 拆分 - POST /api/tools/pdf/split
4. 二维码生成 - POST /api/tools/qrcode
5. 文案小助手 - POST /api/tools/copywriting
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_owner, OwnerContext
from app.core.database import get_db
from app.core.errors import BizError
from app.schemas.common import ok
from app.services import tools as tools_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["M6 工具箱"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get("/access", summary="工具箱权益（V5.0 M8：开业礼包赠 2 个工具 30 天 / 会员全部）")
async def tool_access(request: Request, db: AsyncSession = Depends(get_db)):
    owner = current_owner(request)
    return ok(await tools_service.tool_access(db, owner), _rid(request))


@router.post("/image/compress", summary="图片压缩与格式转换")
async def compress_image(
    request: Request,
    file: Annotated[UploadFile, File(description="图片文件")],
    quality: Annotated[int, Form(description="压缩质量 (1-100)", ge=1, le=100)] = 80,
    format: Annotated[Optional[str], Form(description="目标格式 (jpeg/png/webp)")] = None,
    max_width: Annotated[int, Form(description="最大宽度", ge=1)] = 1920,
    max_height: Annotated[int, Form(description="最大高度", ge=1)] = 1920,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """压缩图片并可转换格式。

    支持 JPEG/PNG/WebP 格式，可调整压缩质量和最大尺寸。
    """
    # 读取文件内容
    content = await file.read()

    # 检查文件大小（最大 20MB）
    if len(content) > 20 * 1024 * 1024:
        raise BizError(40001, "图片文件大小不能超过 20MB")

    # 调用服务
    result = await tools_service.compress_image(
        file_content=content,
        filename=file.filename or "image.jpg",
        quality=quality,
        target_format=format,
        max_width=max_width,
        max_height=max_height,
    )

    return ok(result, _rid(request))


@router.post("/pdf/merge", summary="PDF 合并")
async def merge_pdfs(
    files: Annotated[list[UploadFile], File(description="PDF 文件列表")],
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """合并多个 PDF 文件为一个。

    最多支持 10 个 PDF 文件，每个文件不超过 50MB。
    """
    if not files:
        raise BizError(40001, "请上传至少一个 PDF 文件")

    if len(files) > 10:
        raise BizError(40001, "最多支持 10 个 PDF 文件")

    # 读取所有文件内容
    contents = []
    for idx, file in enumerate(files):
        content = await file.read()

        # 检查单个文件大小（最大 50MB）
        if len(content) > 50 * 1024 * 1024:
            raise BizError(40001, f"第 {idx + 1} 个 PDF 文件大小不能超过 50MB")

        contents.append(content)

    # 调用服务
    result = await tools_service.merge_pdfs(contents)

    return ok(result, _rid(request))


@router.post("/pdf/split", summary="PDF 拆分")
async def split_pdf(
    file: Annotated[UploadFile, File(description="PDF 文件")],
    pages: Annotated[str, Form(description="拆分页码，逗号分隔，如 '3,5,8'")],
    request: Request,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """将 PDF 拆分为多个文件。

    指定拆分页码，例如 "3,5" 表示拆分为 [1-3], [4-5], [6-end]。
    """
    # 解析页码
    try:
        split_pages = [int(p.strip()) for p in pages.split(",") if p.strip()]
    except ValueError:
        raise BizError(40001, "页码格式错误，请使用逗号分隔的数字，如 '3,5,8'")

    if not split_pages:
        raise BizError(40001, "请提供至少一个拆分页码")

    # 读取文件内容
    content = await file.read()

    # 检查文件大小（最大 100MB）
    if len(content) > 100 * 1024 * 1024:
        raise BizError(40001, "PDF 文件大小不能超过 100MB")

    # 调用服务
    result = await tools_service.split_pdf(
        file_content=content,
        split_pages=split_pages,
        filename=file.filename or "document.pdf",
    )

    return ok(result, _rid(request))


@router.post("/qrcode", summary="二维码生成")
async def generate_qrcode(
    request: Request,
    content: Annotated[str, Form(description="二维码内容")],
    size: Annotated[int, Form(description="图片尺寸 (像素)", ge=64, le=1024)] = 256,
    color: Annotated[str, Form(description="二维码颜色 (hex)")] = "#000000",
    background: Annotated[str, Form(description="背景颜色 (hex)")] = "#FFFFFF",
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """生成二维码图片。

    支持自定义颜色、尺寸，内容可以是 URL、文本等。
    """
    # 验证颜色格式
    import re
    if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
        raise BizError(40001, "二维码颜色格式错误，请使用 #RRGGBB 格式")
    if not re.match(r"^#[0-9A-Fa-f]{6}$", background):
        raise BizError(40001, "背景颜色格式错误，请使用 #RRGGBB 格式")

    # 调用服务
    result = await tools_service.generate_qrcode(
        content=content,
        size=size,
        color=color,
        background=background,
    )

    return ok(result, _rid(request))


@router.post("/copywriting", summary="文案小助手")
async def generate_copywriting(
    request: Request,
    category: Annotated[str, Form(description="文案类别 (social_media/ad/promotion/product_description)")],
    keywords: Annotated[str, Form(description="关键词，逗号分隔")],
    tone: Annotated[str, Form(description="语气风格 (friendly/professional/humorous/urgent)")] = "friendly",
    count: Annotated[int, Form(description="生成数量", ge=1, le=10)] = 5,
    owner: OwnerContext = Depends(current_owner),
    db: AsyncSession = Depends(get_db),
):
    """生成营销文案。

    支持 4 种类别和 4 种语气风格，可生成 1-10 条文案。
    """
    # 验证类别
    valid_categories = ["social_media", "ad", "promotion", "product_description"]
    if category not in valid_categories:
        raise BizError(40001, f"文案类别必须是 {', '.join(valid_categories)} 之一")

    # 验证语气
    valid_tones = ["friendly", "professional", "humorous", "urgent"]
    if tone not in valid_tones:
        raise BizError(40001, f"语气风格必须是 {', '.join(valid_tones)} 之一")

    # 解析关键词
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        raise BizError(40001, "请提供至少一个关键词")

    # 调用服务
    result = await tools_service.generate_copywriting(
        category=category,
        keywords=keyword_list,
        tone=tone,
        count=count,
    )

    return ok(result, _rid(request))
