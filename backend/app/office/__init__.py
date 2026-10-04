"""D01–D10 十件交付物生成器（M4）。

合规库：Pillow(图片) / pypdf(PDF) / python-qrcode(二维码) / libvips(图片压缩)。
严禁：PyMuPDF / itext7 / pngquant（AGPL/GPL）。
每个生成函数返回文件本地路径；调用方负责上传对象存储。
"""
from __future__ import annotations

# 交付物清单（与 docs/module-ownership.md 一致）
DELIVERABLES = {
    "D01": ("可行性评分卡", "pdf"),
    "D02": ("回本测算表", "excel"),
    "D03": ("客户画像与获客清单", "pdf"),
    "D04": ("供应商线索与询价话术", "pdf"),
    "D05": ("定价与开业活动", "pdf"),
    "D06": ("开店流程清单", "pdf"),
    "D07": ("获客文案10条", "word"),
    "D08": ("店名与物料", "png"),
    "D09": ("30天行动日历", "excel"),
    "D10": ("风险清单与止损线", "pdf"),
}


def generate_deliverable(code: str, context: dict) -> str:
    """根据 code 分发到对应生成器，返回本地文件路径（占位实现）。"""
    if code not in DELIVERABLES:
        raise ValueError(f"unknown deliverable code: {code}")
    name, ftype = DELIVERABLES[code]
    # TODO(负责人 B): 实现 D01–D10 具体生成逻辑
    # 统一命名：生意快启_交付物名称_生成日期
    # 例：from PIL import Image; from pypdf import PdfWriter; import qrcode
    return f"./tmp/{code}_{name}.{ftype}"
