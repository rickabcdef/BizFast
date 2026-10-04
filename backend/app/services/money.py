"""金额展示的统一口径 - 负责人 A

金额标签必须只在一个地方格式化：前端不重复实现四舍五入，
否则「券后价」与「按钮上的价格」会出现一分钱的差异，用户会认为我们算错账。
"""
from __future__ import annotations


def amount_label(cents: int) -> str:
    """分 → 人类可读的元字符串（去掉多余的 0，如 990 → 9.9，3900 → 39）。"""
    return f"{cents / 100:.2f}".rstrip("0").rstrip(".")
