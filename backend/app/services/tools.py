"""M6 工具箱服务

提供 4 个实用工具：
1. 图片压缩与格式转换 - 使用 Pillow
2. PDF 合并与拆分 - 使用 pypdf
3. 二维码生成 - 使用 qrcode
4. 文案小助手 - 基于模板生成营销文案
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image
from pypdf import PdfReader, PdfWriter
import qrcode

from app.core.config import settings
from app.core.errors import BizError
from app.storage import get_storage

logger = logging.getLogger(__name__)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# 1. 图片压缩与格式转换
# ─────────────────────────────────────────────────────────────────────────────

async def compress_image(
    file_content: bytes,
    filename: str,
    quality: int = 80,
    target_format: Optional[str] = None,
    max_width: int = 1920,
    max_height: int = 1920,
) -> dict:
    """压缩图片并可转换格式。

    Args:
        file_content: 原始图片字节内容
        filename: 原始文件名
        quality: 压缩质量 (1-100)
        target_format: 目标格式 (jpeg/png/webp)，None 则保持原格式
        max_width: 最大宽度
        max_height: 最大高度

    Returns:
        {
            "original_size": 123456,
            "compressed_size": 65432,
            "compression_ratio": 47.0,
            "width": 1920,
            "height": 1080,
            "format": "jpeg",
            "url": "https://..."
        }
    """
    original_size = len(file_content)

    try:
        img = Image.open(io.BytesIO(file_content))
    except Exception as e:
        raise BizError(40001, f"无法解析图片: {str(e)}")

    # 获取原始格式
    orig_format = img.format or "JPEG"

    # 确定目标格式
    if target_format:
        target_format = target_format.upper()
        if target_format == "JPG":
            target_format = "JPEG"
    else:
        target_format = orig_format if orig_format in ("JPEG", "PNG", "WEBP") else "JPEG"

    # 转换 RGBA 到 RGB (JPEG 不支持 alpha)
    if target_format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    # 调整尺寸
    width, height = img.size
    if width > max_width or height > max_height:
        ratio = min(max_width / width, max_height / height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        width, height = new_size

    # 保存压缩后的图片
    output = io.BytesIO()
    save_kwargs = {}

    if target_format == "JPEG":
        save_kwargs = {"quality": quality, "optimize": True}
    elif target_format == "PNG":
        save_kwargs = {"optimize": True}
    elif target_format == "WEBP":
        save_kwargs = {"quality": quality}

    img.save(output, format=target_format, **save_kwargs)
    compressed_bytes = output.getvalue()
    compressed_size = len(compressed_bytes)

    # 计算压缩比
    compression_ratio = round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0

    # 上传到存储
    storage = get_storage()
    ext = target_format.lower()
    if ext == "jpeg":
        ext = "jpg"
    storage_key = f"tools/images/{uuid.uuid4()}.{ext}"
    url = storage.save_bytes(storage_key, compressed_bytes)

    return {
        "original_size": original_size,
        "compressed_size": compressed_size,
        "compression_ratio": compression_ratio,
        "width": width,
        "height": height,
        "format": target_format.lower(),
        "url": url,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. PDF 合并与拆分
# ─────────────────────────────────────────────────────────────────────────────

async def merge_pdfs(file_contents: list[bytes], filename: str = "merged.pdf") -> dict:
    """合并多个 PDF 文件。

    Args:
        file_contents: PDF 文件字节内容列表
        filename: 输出文件名

    Returns:
        {
            "page_count": 15,
            "size": 123456,
            "url": "https://..."
        }
    """
    if not file_contents:
        raise BizError(40001, "未提供 PDF 文件")

    writer = PdfWriter()

    for idx, content in enumerate(file_contents):
        try:
            reader = PdfReader(io.BytesIO(content))
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            raise BizError(40001, f"第 {idx + 1} 个 PDF 解析失败: {str(e)}")

    output = io.BytesIO()
    writer.write(output)
    merged_bytes = output.getvalue()

    # 上传
    storage = get_storage()
    storage_key = f"tools/pdfs/{uuid.uuid4()}.pdf"
    url = storage.save_bytes(storage_key, merged_bytes)

    return {
        "page_count": len(writer.pages),
        "size": len(merged_bytes),
        "url": url,
    }


async def split_pdf(
    file_content: bytes,
    split_pages: list[int],
    filename: str = "split",
) -> dict:
    """拆分 PDF 为多个文件。

    Args:
        file_content: PDF 文件字节内容
        split_pages: 拆分点页码列表 (从 1 开始)
                     例如 [3, 5] 表示拆分为 [1-3], [4-5], [6-end]
        filename: 输出文件名前缀

    Returns:
        {
            "total_pages": 10,
            "parts": [
                {"pages": "1-3", "size": 12345, "url": "..."},
                {"pages": "4-5", "size": 23456, "url": "..."},
                {"pages": "6-10", "size": 34567, "url": "..."}
            ]
        }
    """
    try:
        reader = PdfReader(io.BytesIO(file_content))
    except Exception as e:
        raise BizError(40001, f"PDF 解析失败: {str(e)}")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise BizError(40001, "PDF 文件为空")

    # 验证拆分点
    split_pages = sorted(set(p for p in split_pages if 1 <= p < total_pages))

    # 计算各部分
    parts = []
    storage = get_storage()
    start = 1

    for split_at in split_pages + [total_pages]:
        writer = PdfWriter()
        for page_idx in range(start - 1, split_at):
            writer.add_page(reader.pages[page_idx])

        output = io.BytesIO()
        writer.write(output)
        part_bytes = output.getvalue()

        # 上传
        storage_key = f"tools/pdfs/{uuid.uuid4()}_part{len(parts) + 1}.pdf"
        url = storage.save_bytes(storage_key, part_bytes)

        parts.append({
            "pages": f"{start}-{split_at}",
            "size": len(part_bytes),
            "url": url,
        })
        start = split_at + 1

    return {
        "total_pages": total_pages,
        "parts": parts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. 二维码生成
# ─────────────────────────────────────────────────────────────────────────────

async def generate_qrcode(
    content: str,
    size: int = 256,
    color: str = "#000000",
    background: str = "#FFFFFF",
) -> dict:
    """生成二维码图片。

    Args:
        content: 二维码内容
        size: 图片尺寸 (像素)
        color: 二维码颜色 (hex)
        background: 背景颜色 (hex)

    Returns:
        {
            "size": 256,
            "url": "https://..."
        }
    """
    if not content:
        raise BizError(40001, "二维码内容不能为空")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    img = qr.make_image(fill_color=color, back_color=background)

    # 调整尺寸
    img = img.resize((size, size), Image.Resampling.NEAREST)

    # 转换为 PNG
    output = io.BytesIO()
    img.save(output, format="PNG")
    png_bytes = output.getvalue()

    # 上传
    storage = get_storage()
    storage_key = f"tools/qrcodes/{uuid.uuid4()}.png"
    url = storage.save_bytes(storage_key, png_bytes)

    return {
        "size": size,
        "url": url,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. 文案小助手
# ─────────────────────────────────────────────────────────────────────────────

async def generate_copywriting(
    category: str,
    keywords: list[str],
    tone: str = "friendly",
    count: int = 5,
) -> dict:
    """生成营销文案。

    Args:
        category: 文案类别 (social_media/ad/promotion/product_description)
        keywords: 关键词列表
        tone: 语气风格 (friendly/professional/humorous/urgent)
        count: 生成数量

    Returns:
        {
            "count": 5,
            "items": [
                {"title": "...", "content": "..."},
                ...
            ]
        }
    """
    if not keywords:
        raise BizError(40001, "请提供至少一个关键词")

    # 文案模板
    templates = {
        "social_media": {
            "friendly": [
                "发现宝藏好物！{keywords}，用过就回不去了～",
                "今天的快乐是{keywords}给的，分享给姐妹们！",
                "被{keywords}种草了，性价比超高，必须安利！",
                "日常分享：{keywords}使用心得，真的绝绝子！",
                "谁懂啊！{keywords}居然这么好用，相见恨晚！",
            ],
            "professional": [
                "专业推荐：{keywords}，行业领先的解决方案。",
                "深度评测：{keywords}的核心优势与适用场景分析。",
                "为什么选择{keywords}？从三个维度为您解读。",
                "行业洞察：{keywords}如何改变我们的工作方式。",
                "案例分析：{keywords}在企业级应用中的表现。",
            ],
            "humorous": [
                "用了{keywords}之后，我整个人都升华了（夸张了但好用是真的）",
                "本来不信邪，试了下{keywords}，真香警告！",
                "老板问我为什么效率这么高，我偷偷笑了：{keywords}",
                "别人都在卷，我在用{keywords}躺赢（不是）",
                "如果{keywords}是个人，我愿意和它结婚！",
            ],
            "urgent": [
                "限时特惠！{keywords}今日下单立减，手慢无！",
                "最后3小时！{keywords}库存告急，错过等一年！",
                "紧急通知：{keywords}即将涨价，现在入手最划算！",
                "仅剩最后100件！{keywords}抢购进行中！",
                "倒计时开始！{keywords}优惠即将结束，立即行动！",
            ],
        },
        "ad": {
            "friendly": [
                "想要提升生活品质？{keywords}帮你实现！",
                "每天进步一点点，从{keywords}开始。",
                "给自己一个惊喜，{keywords}值得拥有。",
                "生活需要仪式感，{keywords}让日常更精致。",
                "选择{keywords}，选择更好的自己。",
            ],
            "professional": [
                "{keywords}：专业级解决方案，助力业务增长。",
                "选择{keywords}，让效率提升300%。",
                "企业级{keywords}，稳定可靠，值得信赖。",
                "{keywords}：经过10000+用户验证的优质产品。",
                "投资{keywords}，回报看得见。",
            ],
            "humorous": [
                "别问，问就是{keywords}好用！",
                "{keywords}：用了都说好，不用不知道。",
                "人生苦短，我用{keywords}。",
                "不是所有的{keywords}都叫{keywords}（懂的都懂）",
                "用过{keywords}之后，其他都是将就。",
            ],
            "urgent": [
                "立即抢购{keywords}，限时5折优惠！",
                "{keywords}限量特惠，仅剩最后名额！",
                "马上行动！{keywords}今日特价，明日恢复原价！",
                "别犹豫了！{keywords}库存即将售罄！",
                "最后机会！{keywords}限量特惠，错过再等一年！",
            ],
        },
        "promotion": {
            "friendly": [
                "新店开业！{keywords}全场8折，欢迎来逛逛～",
                "周年庆啦！{keywords}买一送一，感谢大家支持！",
                "会员日特惠！{keywords}专享折扣，快来薅羊毛！",
                "节日特惠！{keywords}限时降价，给自己一个礼物吧！",
                "新品上市！{keywords}首发优惠，先到先得！",
            ],
            "professional": [
                "年度大促：{keywords}全线产品优惠30%。",
                "企业客户专享：{keywords}批量采购额外折扣。",
                "战略合作伙伴优惠：{keywords}定制化方案特价。",
                "季度促销：{keywords}限时优惠，助力企业降本增效。",
                "新品发布：{keywords}系列，首发限量特惠。",
            ],
            "humorous": [
                "老板疯了！{keywords}亏本甩卖，买到就是赚到！",
                "双十一都不一定有的价格！{keywords}今天超低价！",
                "打工人福利！{keywords}特价，对自己好一点！",
                "别问为什么这么便宜，问就是{keywords}在做活动！",
                "今天的{keywords}价格，连我自己都吓一跳！",
            ],
            "urgent": [
                "限时24小时！{keywords}全场5折，手慢无！",
                "最后100件！{keywords}清仓特卖，售完即止！",
                "紧急促销！{keywords}今日下单立减200元！",
                "倒计时开始！{keywords}优惠仅剩最后3小时！",
                "库存告急！{keywords}仅剩少量，立即抢购！",
            ],
        },
        "product_description": {
            "friendly": [
                "这款{keywords}真的是我的心头好，用了一段时间必须分享给你们！",
                "作为一个{keywords}重度用户，这款真的让我惊艳了！",
                "终于找到好用的{keywords}了，性价比超高，推荐给大家！",
                "日常必备的{keywords}，这款用下来体验最好！",
                "被朋友安利的{keywords}，用了之后真的爱上了！",
            ],
            "professional": [
                "专业级{keywords}，采用先进工艺，品质有保障。",
                "这款{keywords}经过严格测试，性能稳定可靠。",
                "高端{keywords}，满足专业用户的严苛需求。",
                "行业领先的{keywords}，多项专利技术加持。",
                "企业级{keywords}解决方案，助力业务高效运转。",
            ],
            "humorous": [
                "这款{keywords}好用到什么程度呢？用完一个立马又囤了三个！",
                "自从用了这个{keywords}，我感觉自己人生都升华了（夸张了但好用是真的）",
                "本来抱着试试看的心态买了这个{keywords}，结果真香了！",
                "这个{keywords}简直是我的救星，没有它我都不知道怎么活！",
                "用了这个{keywords}之后，我感觉自己就是整条街最靓的仔！",
            ],
            "urgent": [
                "限时特惠！这款{keywords}今日下单立减50元！",
                "库存仅剩最后50件！这款{keywords}即将售罄！",
                "新品首发特惠！{keywords}限时特价，错过等一年！",
                "最后机会！这款{keywords}优惠即将结束，立即抢购！",
                "限量特惠！{keywords}今日下单赠送超值礼品！",
            ],
        },
    }

    # 获取对应类别和语气的模板
    category_templates = templates.get(category, templates["social_media"])
    tone_templates = category_templates.get(tone, category_templates["friendly"])

    # 生成文案
    keywords_str = "、".join(keywords)
    items = []
    for i in range(min(count, len(tone_templates))):
        template = tone_templates[i % len(tone_templates)]
        content = template.format(keywords=keywords_str)
        items.append({
            "title": f"文案 {i + 1}",
            "content": content,
        })

    return {
        "count": len(items),
        "items": items,
    }
