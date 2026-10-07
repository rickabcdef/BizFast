"""D01–D10 十件交付物生成器（M4）。

合规库：Pillow(图片) / pypdf(PDF) / python-qrcode(二维码) / reportlab(PDF) / openpyxl(Excel) / python-docx(Word)。
严禁：PyMuPDF / itext7 / pngquant（AGPL/GPL）。

设计：**内容与渲染分离**。
- 每种交付物的「文字内容」只在 `_doc_content` / `_table_content` 里定义一次；
- 具体渲染（PDF / Word / TXT / Excel / PNG / SVG）由 `_render` 统一分发，
  因此同一交付物可以低成本地交付多种格式（PRD 4.4.1）。
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

# 交付物清单（与 docs/module-ownership.md 一致）：code -> (名称, 主格式)
DELIVERABLES: dict[str, tuple[str, str]] = {
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

# PRD 4.4.1：部分交付物同时交付多格式（主格式排第一，与 DELIVERABLES 一致）。
# D03/D06 = PDF+Word、D07 = Word+TXT、D08 = PNG+SVG、D09 = PDF+Excel，其余单格式。
DELIVERABLE_FORMATS: dict[str, list[str]] = {
    "D01": ["pdf"],
    "D02": ["excel"],
    "D03": ["pdf", "word"],
    "D04": ["pdf"],
    "D05": ["pdf"],
    "D06": ["pdf", "word"],
    "D07": ["word", "txt"],
    "D08": ["png", "svg"],
    "D09": ["excel", "pdf"],
    "D10": ["pdf"],
}

# 格式 -> 文件扩展名（前端 downloadName / ZIP 内中文命名共用同一份映射语义）
FILE_EXT: dict[str, str] = {
    "pdf": "pdf",
    "excel": "xlsx",
    "word": "docx",
    "png": "png",
    "svg": "svg",
    "txt": "txt",
    "zip": "zip",
}

# V5.0 第 7.2 闸门 3「模板化交付」：10 件交付物中 7 件模板填充、只有 3 件走 AI 实时生成。
# V5.0 需求 3.1 明确这 3 件的名字：**可行性评分（D01）、个性化文案（D07）、物料定制（D08）**。
# 其余 7 件仅替换用户输入的变量（城市/资金/时间/商机名），把单次成本压在 3.5 元以内。
AI_DELIVERABLES: frozenset[str] = frozenset({"D01", "D07", "D08"})
TEMPLATE_DELIVERABLES: frozenset[str] = frozenset(DELIVERABLES) - AI_DELIVERABLES

# 中文字体路径（系统自带，跨平台 fallback）
_FONT_PATHS = [
    # Windows
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

_FONT_NAME = "Helvetica"  # reportlab fallback


def _find_font() -> str | None:
    for p in _FONT_PATHS:
        if os.path.exists(p):
            return p
    return None


def _tmp_dir(order_id: str) -> Path:
    """为每个订单创建临时目录，返回路径。"""
    d = Path(tempfile.gettempdir()) / "bizfast_package" / order_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ──────────────────────────────────────────────
#  渲染层
# ──────────────────────────────────────────────
def _make_pdf(path: Path, title: str, sections: list[dict]) -> str:
    """用 reportlab 生成一份中文 PDF。

    sections: [{"heading": "...", "body": "..."}, ...]
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph

    # reportlab 5.0 起把 ttfont 重命名为 ttfonts；这里做兼容导入，
    # 避免因版本差异导致 D01/D03/D04/D05/D06/D10 六份 PDF 全部生成失败。
    try:
        from reportlab.pdfbase.ttfonts import TTFont  # reportlab >= 5.0
    except ImportError:  # pragma: no cover - 旧版本
        from reportlab.pdfbase.ttfont import TTFont  # reportlab < 5.0

    # 注册中文字体
    font_name = "Helvetica"
    font_path = _find_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("CNFont", font_path))
            font_name = "CNFont"
        except Exception:
            font_name = "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CNTitle", parent=styles["Title"], fontName=font_name, fontSize=20, leading=28,
        spaceAfter=12 * mm,
    )
    heading_style = ParagraphStyle(
        "CNHeading", parent=styles["Heading2"], fontName=font_name, fontSize=14, leading=20,
        spaceBefore=8 * mm, spaceAfter=4 * mm,
    )
    body_style = ParagraphStyle(
        "CNBody", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=16,
        spaceAfter=3 * mm,
    )

    doc = BaseDocTemplate(
        str(path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="main",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story = [Paragraph(_safe(title), title_style)]
    for sec in sections:
        if sec.get("heading"):
            story.append(Paragraph(_safe(sec["heading"]), heading_style))
        if sec.get("body"):
            for line in sec["body"].split("\n"):
                if line.strip():
                    story.append(Paragraph(_safe(line.strip()), body_style))

    doc.build(story)
    return str(path)


def _safe(text: str) -> str:
    """reportlab 段落是迷你 XML：转义 & < >，避免内容里的符号把 XML 打断。"""
    return _xml_escape(str(text), {"'": "&#39;", '"': "&quot;"})


def _make_excel(path: Path, title: str, headers: list[str], rows: list[list]) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]  # Excel sheet name max 31 chars

    # 标题行
    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1)
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal="center")

    # 表头
    header_fill = PatternFill(start_color="165DFF", end_color="165DFF", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 数据行
    for row in rows:
        ws.append(row)

    # 自动列宽（按列号遍历：ws.columns 在存在合并单元格时会返回 MergedCell，
    # 其没有 column_letter 属性，直接用列号换算列字母更稳妥）
    for col_idx in range(1, len(headers) + 1):
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            max_len = max(max_len, len(str(value or "")))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

    wb.save(str(path))
    return str(path)


def _make_word(path: Path, title: str, sections: list[dict]) -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    heading = doc.add_heading(title, level=0)
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0x16, 0x5D, 0xFF)

    for sec in sections:
        if sec.get("heading"):
            doc.add_heading(sec["heading"], level=2)
        if sec.get("body"):
            for line in sec["body"].split("\n"):
                if line.strip():
                    p = doc.add_paragraph(line.strip())
                    p.style.font.size = Pt(11)

    doc.save(str(path))
    return str(path)


def _make_txt(path: Path, title: str, sections: list[dict]) -> str:
    """纯文本渲染（D07 = Word + TXT，方便直接复制到微信/短视频脚本框）。"""
    lines: list[str] = [title, "=" * 30, ""]
    for sec in sections:
        if sec.get("heading"):
            heading = str(sec["heading"])
            lines.append(heading)
            lines.append("-" * len(heading))
        if sec.get("body"):
            lines.extend(sec["body"].split("\n"))
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return str(path)


# ──────────────────────────────────────────────
#  内容层：文字内容只定义一次，多格式复用
# ──────────────────────────────────────────────
def _doc_content(code: str, ctx: dict) -> tuple[str, list[dict]]:
    """返回 (标题, sections)，供 PDF / Word / TXT 渲染。"""
    opp = ctx.get("opportunity", {}) or {}
    city = ctx.get("city", "未知城市")

    if code == "D01":
        score = ctx.get("score", 85)
        return "可行性评分卡", [
            {"heading": "基本信息", "body": f"城市：{city}\n启动资金档位：{ctx.get('capital_label', '未设定')}\n商机名称：{opp.get('title', '待定')}\n评估日期：{_today_str()}"},
            {"heading": "综合可行性评分", "body": f"总分：{score} / 100\n\n评分维度：\n· 市场需求匹配度：{min(score + 5, 100)}分\n· 资金门槛适配度：{min(score + 3, 100)}分\n· 回本周期合理性：{max(score - 5, 60)}分\n· 竞争饱和度：{max(score - 8, 55)}分\n· 上手难度：{min(score + 2, 100)}分"},
            {"heading": "核心优势", "body": opp.get("summary", "轻资产启动，回本周期短，适合新手创业者。")},
            {"heading": "关键风险", "body": "\n".join(f"· {r}" for r in (opp.get("risks") or ["市场竞争激烈", "现金流管理不当"]))},
            {"heading": "止损建议", "body": opp.get("stop_loss", "连续30天日均订单低于10单时，考虑调整策略或退出。")},
        ]

    if code == "D03":
        return "客户画像与获客清单", [
            {"heading": "目标客户画像", "body": f"所在城市：{city}\n年龄段：25-45岁\n消费特征：注重性价比，愿意为便利付费\n触达渠道：微信社群、抖音、小红书、线下社区"},
            {"heading": "第一个客户在哪", "body": opp.get("first_customer", "通过小区业主群、周边便利店门口、社区广场等渠道获取第一批客户。")},
            {"heading": "首月获客清单", "body": "第1周：建立200人微信群，发布3条有价值内容\n第2周：线下地推，覆盖周边3个小区，发放200份传单\n第3周：朋友圈广告测试，预算200元，目标曝光5000次\n第4周：老客户转介绍激励，每推荐1人返现5元"},
            {"heading": "长期获客渠道", "body": "· 抖音短视频：每周3条，展示产品/服务过程\n· 小红书种草：每月5篇图文笔记\n· 社区合作：与物业、快递站、便利店建立互推关系\n· 私域运营：每日群内互动，每周1次限时活动"},
        ]

    if code == "D04":
        return "供应商线索与询价话术", [
            {"heading": "核心供应商类型", "body": "· 线上批发平台：1688、拼多多批发、义乌购\n· 本地批发市场：当地综合批发市场、专业批发市场\n· 厂家直供：通过行业展会、企查查查找本地生产厂家"},
            {"heading": "询价话术模板", "body": "开场：「您好，我是刚起步的小商家，想长期合作，请问最低起批量是多少？」\n砍价：「我看其他家价格在XX，您这边能不能给个长期合作价？」\n账期：「前期小批量现金结算，后面量大了能不能月结？」\n验货：「第一批货我先拿样品，质量好再批量下单。」"},
            {"heading": "供应商筛选标准", "body": "1. 价格合理：不高于市场均价的110%\n2. 供货稳定：能保证3天内发货\n3. 售后保障：支持7天无理由退换\n4. 配合度高：愿意小批量试单"},
        ]

    if code == "D05":
        margin = opp.get("margin_pct", 35)
        return "定价与开业活动", [
            {"heading": "定价策略", "body": f"建议毛利率：{margin}%\n\n定价公式：售价 = 成本 ÷ (1 - 毛利率)\n\n示例：\n· 成本10元 → 售价 10 ÷ 0.65 ≈ 15.4元 → 建议定价15-16元\n· 成本50元 → 售价 50 ÷ 0.65 ≈ 76.9元 → 建议定价75-80元\n· 成本100元 → 售价 100 ÷ 0.65 ≈ 153.8元 → 建议定价150-160元"},
            {"heading": "开业活动方案一：限时折扣", "body": "活动时间：开业前3天\n内容：全场8折 + 消费满50送小礼品\n预算：礼品成本约500元\n预期：首日客流100+，3天累计300+"},
            {"heading": "开业活动方案二：老带新", "body": "活动时间：开业首月\n内容：老客户推荐1人下单，双方各减10元\n预算：按首月50单计算，补贴约500元\n预期：获客50人，留存率60%以上"},
            {"heading": "开业活动方案三：社群裂变", "body": "活动时间：开业首周\n内容：转发海报到朋友圈集28赞，免费领体验装\n预算：体验装成本约300元（50份）\n预期：海报曝光5000+，新增微信好友100+"},
        ]

    if code == "D06":
        return "开店流程清单", [
            {"heading": "第一阶段：准备期（第1-7天）", "body": "□ 确定经营项目和商业模式\n□ 市场调研：走访周边3公里，记录同类店铺数量和价格\n□ 确定启动资金预算，预留3个月流动资金\n□ 注册个体工商户（线上可办理）\n□ 开设对公账户或经营专用微信/支付宝"},
            {"heading": "第二阶段：筹备期（第8-14天）", "body": "□ 寻找供应商，首批进货\n□ 搭建线上渠道（微信群/小程序/抖音账号）\n□ 准备物料：价目表、收款码、名片\n□ 拍摄产品/服务照片和视频素材\n□ 制定首月营销计划"},
            {"heading": "第三阶段：试运营（第15-21天）", "body": "□ 小范围试运营，收集前10个客户反馈\n□ 根据反馈调整产品/服务/价格\n□ 建立客户微信群，沉淀私域流量\n□ 记录每日收支，计算真实毛利率"},
            {"heading": "第四阶段：正式运营（第22-30天）", "body": "□ 启动开业活动\n□ 扩大推广范围\n□ 建立日常运营SOP\n□ 设定月度目标和止损线"},
        ]

    if code == "D07":
        title = opp.get("title", "优质小生意")
        return "获客文案10条", [
            {"heading": "朋友圈文案 1：开业宣传", "body": f"🎉 正式开张！\n经过{city}市场调研，我决定做{title}这个方向。\n首批客户专享价，比市场价低20%。\n扫码加我微信，前50名送体验装！"},
            {"heading": "朋友圈文案 2：产品种草", "body": "说实话，一开始我也觉得这东西没啥特别的。\n直到自己用了之后...真香！\n好东西就要分享出来，需要的私信我～"},
            {"heading": "朋友圈文案 3：客户好评", "body": "今天又收到一位客户的感谢消息😊\n做这行最有成就感的就是看到客户满意。\n有需要的朋友随时找我，价格绝对实在！"},
            {"heading": "朋友圈文案 4：限时活动", "body": "⏰ 限时3天！\n本周末下单立减10元，老客户再送小礼品。\n名额有限，先到先得～\n（别怪我没提醒你哦）"},
            {"heading": "朋友圈文案 5：日常分享", "body": "创业第30天，记录一下：\n本月收入：XX元\n客户数量：XX人\n最大感悟：坚持发朋友圈真的有用！\n明天继续加油💪"},
            {"heading": "抖音短视频文案 6：创业故事", "body": "标题：裸辞后靠XX月入过万，我做了什么？\n开头：「别急着划走，这可能是你今年看到最真实的创业故事。」\n内容：讲述从0到1的过程，重点讲遇到的困难和解决方法。\n结尾：关注我，持续分享创业干货。"},
            {"heading": "抖音短视频文案 7：干货分享", "body": "标题：做XX生意，这3个坑千万别踩！\n开头：「花了我5000块学费才总结出来的经验，今天免费告诉你。」\n内容：分享3个常见错误和正确做法。\n结尾：觉得有用就点赞收藏，下次找得到。"},
            {"heading": "小红书文案 8：测评笔记", "body": f"标题：{title}真实体验｜做了30天的真实感受\n正文：\n✅ 优点：投入低、上手快、时间灵活\n❌ 缺点：前期获客难、需要耐心\n💡 建议：先从身边人做起，不要一上来就大投入\n📊 数据：第1个月收入XX元，客户XX人"},
            {"heading": "社群文案 9：裂变活动", "body": "🎁 福利时间！\n转发本条消息到朋友圈，集满28个赞\n截图发我，免费领XX一份！\n活动截止：本周日晚12点\n（仅限前100名，手慢无）"},
            {"heading": "社群文案 10：老客维护", "body": "感谢各位老朋友一路支持❤️\n这个月给大家准备了专属福利：\n1. 老客户回购享9折\n2. 推荐新朋友下单，双方各减5元\n3. 本月消费满100元送神秘礼物\n有需要的直接群里@我就行～"},
        ]

    if code == "D10":
        risks = opp.get("risks") or [
            "市场竞争激烈，同类商家过多导致获客成本上升",
            "现金流管理不当，过度囤货导致资金链断裂",
            "政策变化风险，如经营许可、行业监管调整",
        ]
        risk_sections = [{"heading": f"风险 {i + 1}", "body": r} for i, r in enumerate(risks)]
        return "风险清单与止损线", [
            {"heading": "核心风险清单", "body": ""},
            *risk_sections,
            {"heading": "止损线设定", "body": opp.get("stop_loss", "连续30天日均订单低于10单时，考虑退出。")},
            {"heading": "风险应对策略", "body": "1. 控制投入：启动资金不超过可承受损失的50%\n2. 快速验证：先用最小成本测试市场反应\n3. 设置退出条件：明确什么情况下停止\n4. 分散风险：不要把所有积蓄都投入一个项目\n5. 保持学习：持续关注行业动态和竞品信息"},
            {"heading": "紧急预案", "body": "· 供应商断供：保持至少2家备选供应商\n· 客户投诉：24小时内响应，建立标准处理流程\n· 资金紧张：预留3个月运营资金，必要时缩减规模\n· 合伙人退出：提前约定退出机制和清算方式"},
        ]

    raise ValueError(f"unknown doc deliverable code: {code}")


def _table_content(code: str, ctx: dict) -> tuple[str, list[str], list[list]]:
    """返回 (标题, 表头, 数据行)，供 Excel / PDF(表格转文字) 渲染。"""
    opp = ctx.get("opportunity", {}) or {}

    if code == "D02":
        capital = ctx.get("capital", 5000)
        payback = opp.get("payback_months", 3)
        margin = opp.get("margin_pct", 35)
        headers = ["月份", "预计月收入(元)", "月固定成本(元)", "月毛利(元)", "累计利润(元)", "是否回本"]
        monthly_revenue = capital * 0.8  # 估算月收入约为启动资金的80%
        monthly_cost = monthly_revenue * 0.3
        monthly_profit = monthly_revenue * (margin / 100) - monthly_cost

        rows: list[list] = []
        cumulative = 0.0
        for m in range(1, 13):
            cumulative += monthly_profit
            rows.append([
                f"第{m}月",
                round(monthly_revenue),
                round(monthly_cost),
                round(monthly_profit),
                round(cumulative),
                "是" if cumulative >= capital else "否",
            ])
        return "回本测算表", headers, rows

    if code == "D09":
        headers = ["天数", "日期类型", "主要任务", "具体行动", "预期产出", "备注"]
        rows = [
            [1, "准备", "市场调研", "走访周边3公里，记录同类商家", "调研笔记1份", ""],
            [2, "准备", "确定方向", "对比3个方向，选定最终项目", "项目决策表", ""],
            [3, "准备", "注册办理", "线上注册个体工商户", "营业执照", ""],
            [4, "准备", "供应商对接", "联系3家供应商，获取报价", "供应商对比表", ""],
            [5, "准备", "首批进货", "确定首批商品清单，下单采购", "首批货物", "控制在预算30%以内"],
            [6, "准备", "渠道搭建", "建立微信群、抖音账号", "线上渠道就绪", ""],
            [7, "准备", "物料准备", "拍摄产品照片、制作价目表", "物料包", ""],
            [8, "试运营", "内测启动", "邀请5位朋友体验", "内测反馈", ""],
            [9, "试运营", "调整优化", "根据内测反馈调整", "优化方案", ""],
            [10, "试运营", "社群推广", "在3个业主群发布开业信息", "首批客户20人", ""],
            [11, "试运营", "朋友圈宣传", "发布开业海报和活动", "咨询量30+", ""],
            [12, "试运营", "地推获客", "周边小区发放传单200份", "新增客户10人", ""],
            [13, "试运营", "线上推广", "抖音发布第1条短视频", "曝光1000+", ""],
            [14, "试运营", "数据复盘", "统计首周数据，计算毛利率", "周报", ""],
            [15, "放量", "开业活动", "启动限时折扣活动", "当日订单50+", ""],
            [16, "放量", "裂变推广", "老带新活动上线", "新增客户30人", ""],
            [17, "放量", "内容营销", "小红书发布种草笔记", "笔记曝光2000+", ""],
            [18, "放量", "社群运营", "群内互动+限时秒杀", "群活跃度提升50%", ""],
            [19, "放量", "渠道拓展", "对接2个社区合作点", "合作点就绪", ""],
            [20, "放量", "供应链优化", "根据销量调整进货策略", "优化供应商清单", ""],
            [21, "放量", "阶段复盘", "两周数据汇总分析", "半月报", ""],
            [22, "稳定", "日常运营", "建立每日运营SOP", "SOP文档", ""],
            [23, "稳定", "客户维护", "回访老客户，收集好评", "好评素材5条", ""],
            [24, "稳定", "内容持续", "发布第3条抖音+第2篇小红书", "内容发布", ""],
            [25, "稳定", "财务整理", "月度收支统计", "月报", ""],
            [26, "稳定", "策略调整", "根据数据调整获客策略", "策略调整方案", ""],
            [27, "稳定", "库存管理", "盘点库存，优化周转", "库存报告", ""],
            [28, "稳定", "目标设定", "设定下月目标和计划", "月度计划", ""],
            [29, "稳定", "经验总结", "总结首月经验教训", "经验手册", ""],
            [30, "稳定", "月度复盘", "全面复盘，决定下一步", "月度复盘报告", "关键决策点"],
        ]
        return "30天行动日历", headers, rows

    raise ValueError(f"unknown table deliverable code: {code}")


# ──────────────────────────────────────────────
#  D08 宣传物料（PNG + SVG 双格式）
# ──────────────────────────────────────────────
def _poster_fields(ctx: dict) -> dict:
    opp = ctx.get("opportunity", {}) or {}
    city = ctx.get("city", "")
    return {
        "shop_name": f"{city}{opp.get('title', '小店')}工作室",
        "subtitle": "生意快启 · 为你定制",
        "qr_text": "扫码了解详情",
        "qr_data": f"bizfast://shop/{opp.get('id', 'demo')}",
        "summary": opp.get("summary", "轻资产创业，快速回本"),
        "footer": f"📍 {city}  |  💰 启动资金 {ctx.get('capital_label', '')}",
    }


def _make_poster_png(path: Path, ctx: dict) -> str:
    """用 Pillow 生成 800x1200 宣传海报。"""
    from PIL import Image, ImageDraw, ImageFont

    f = _poster_fields(ctx)

    img = Image.new("RGB", (800, 1200), "#0F172A")
    draw = ImageDraw.Draw(img)

    # 顶部渐变背景色块（深蓝 → 品牌蓝）
    for y in range(400):
        r = 22
        g = int(23 + (93 - 23) * y / 400)
        b = int(42 + (255 - 42) * y / 400)
        draw.line([(0, y), (800, y)], fill=(r, g, b))

    # 尝试加载中文字体（缺失时降级为默认位图字体，不阻断交付）
    font_large = font_medium = font_small = None
    font_path = _find_font()
    if font_path:
        try:
            font_large = ImageFont.truetype(font_path, 56)
            font_medium = ImageFont.truetype(font_path, 28)
            font_small = ImageFont.truetype(font_path, 20)
        except Exception:
            pass
    if font_large is None:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    draw.text((400, 120), f["shop_name"], fill="white", font=font_large, anchor="mt")
    draw.text((400, 200), f["subtitle"], fill=(230, 235, 255), font=font_medium, anchor="mt")

    # 二维码区域
    try:
        import qrcode

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(f["qr_data"])
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#165DFF", back_color="white").convert("RGB")
        qr_img = qr_img.resize((200, 200))
        img.paste(qr_img, (300, 280))
        draw.text((400, 510), f["qr_text"], fill="white", font=font_small, anchor="mt")
    except Exception:
        draw.rectangle([(300, 280), (500, 480)], outline="#7B61FF", width=2)
        draw.text((400, 380), "QR Code", fill="#7B61FF", font=font_small, anchor="mm")

    # 底部信息
    draw.text((400, 580), f["summary"], fill="white", font=font_small, anchor="mt")
    draw.text((400, 620), f["footer"], fill=(235, 240, 255), font=font_small, anchor="mt")

    img.save(str(path), quality=95)
    return str(path)


def _make_poster_svg(path: Path, ctx: dict) -> str:
    """同款海报的矢量版（SVG 无字体依赖，任何环境都可渲染中文标题）。"""
    f = _poster_fields(ctx)
    e = _xml_escape
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200" viewBox="0 0 800 1200">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#165DFF"/>
      <stop offset="100%" stop-color="#16172A"/>
    </linearGradient>
  </defs>
  <rect width="800" height="1200" fill="#0F172A"/>
  <rect width="800" height="400" fill="url(#bg)"/>
  <text x="400" y="150" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="56" font-weight="bold" fill="#FFFFFF">{e(f['shop_name'])}</text>
  <text x="400" y="215" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="28" fill="#E6EBFF">{e(f['subtitle'])}</text>
  <rect x="300" y="280" width="200" height="200" rx="12" fill="#FFFFFF" stroke="#7B61FF" stroke-width="3"/>
  <text x="400" y="388" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="18" fill="#165DFF">QR</text>
  <text x="400" y="510" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="20" fill="#FFFFFF">{e(f['qr_text'])}</text>
  <text x="400" y="580" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="20" fill="#FFFFFF">{e(f['summary'])}</text>
  <text x="400" y="620" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="20" fill="#E6EBFF">{e(f['footer'])}</text>
  <text x="400" y="1140" text-anchor="middle" font-family="Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif" font-size="18" fill="#8B93B8">生意快启 · 开店前 3 分钟拿到可执行的启动包</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")
    return str(path)


# ──────────────────────────────────────────────
#  统一分发
# ──────────────────────────────────────────────
def _render(code: str, fmt: str, ctx: dict, out_dir: Path) -> str:
    """把某交付物渲染成指定格式，返回本地文件路径。"""
    name = DELIVERABLES[code][0]
    ext = FILE_EXT.get(fmt, "bin")
    path = out_dir / f"{code}_{name}.{ext}"

    if code == "D08":
        if fmt == "png":
            return _make_poster_png(path, ctx)
        if fmt == "svg":
            return _make_poster_svg(path, ctx)
        raise ValueError(f"D08 不支持格式 {fmt}")

    if code in ("D02", "D09"):
        title, headers, rows = _table_content(code, ctx)
        if fmt == "excel":
            return _make_excel(path, title, headers, rows)
        if fmt == "pdf":
            # 表格 → 文字版 PDF（同内容，便于打印）
            return _make_pdf(path, title, _table_as_sections(code, headers, rows))
        raise ValueError(f"{code} 不支持格式 {fmt}")

    title, sections = _doc_content(code, ctx)
    if fmt == "pdf":
        return _make_pdf(path, title, sections)
    if fmt == "word":
        return _make_word(path, title, sections)
    if fmt == "txt":
        return _make_txt(path, title, sections)
    raise ValueError(f"{code} 不支持格式 {fmt}")


_D09_WEEK_TITLES = {
    "准备": "第一阶段：准备期（第1-7天）",
    "试运营": "第二阶段：试运营（第8-14天）",
    "放量": "第三阶段：放量（第15-21天）",
    "稳定": "第四阶段：稳定运营（第22-30天）",
}


def _table_as_sections(code: str, headers: list[str], rows: list[list]) -> list[dict]:
    """把表格数据转成 PDF 段落（保持内容一致，便于打印与转 PDF）。"""
    if code == "D09":
        sections: list[dict] = []
        buckets: dict[str, list[str]] = {}
        for row in rows:
            day, phase, task, action, output, note = row
            line = f"第{day}天 · {task}：{action}｜预期产出：{output}"
            if note:
                line += f"｜备注：{note}"
            buckets.setdefault(str(phase), []).append(line)
        for phase, lines in buckets.items():
            sections.append({"heading": _D09_WEEK_TITLES.get(phase, phase), "body": "\n".join(lines)})
        return sections

    # 通用表格：表头一行 + 每行用「 | 」拼接
    body_lines = [" | ".join(str(h) for h in headers)]
    body_lines.append("-" * 40)
    for row in rows:
        body_lines.append(" | ".join(str(c) for c in row))
    return [{"heading": "明细", "body": "\n".join(body_lines)}]


def generate_formats(code: str, context: dict) -> dict[str, str]:
    """生成某交付物的全部格式，返回 {format: local_path}。

    单个格式失败不影响其它格式（调用方按返回结果落库）。
    """
    if code not in DELIVERABLES:
        raise ValueError(f"unknown deliverable code: {code}")

    context = {**context, "order_id": context.get("order_id", "demo")}
    out_dir = _tmp_dir(context["order_id"])

    result: dict[str, str] = {}
    for fmt in DELIVERABLE_FORMATS[code]:
        result[fmt] = _render(code, fmt, context, out_dir)
    return result


def generate_deliverable(code: str, context: dict) -> str:
    """兼容入口：生成主格式，返回本地文件路径。

    context 需包含：order_id / city / capital / capital_label / opportunity / score。
    """
    formats = generate_formats(code, context)
    return formats[DELIVERABLES[code][1]]


def generate_all(order_id: str, context: dict) -> dict[str, tuple[str, str]]:
    """生成全部 10 件交付物的全部格式，返回 {code: (format, local_path)} 扁平结果。"""
    context = {**context, "order_id": order_id}
    results: dict[str, tuple[str, str]] = {}
    for code in sorted(DELIVERABLES.keys()):
        for fmt, path in generate_formats(code, context).items():
            results[f"{code}:{fmt}"] = (fmt, path)
    return results
