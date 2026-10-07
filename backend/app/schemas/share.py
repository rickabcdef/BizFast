"""D 端分享/增长 schema（M8 分享与增长 / M8-03 邀请 / M8-04 回收）。对外统一 camelCase。"""
from __future__ import annotations

from app.schemas.common import CamelModel


class ShareCardIn(CamelModel):
    """生成成果分享卡片（M8-01）。卡片图由前端 canvas 渲染，后端只落库元数据 + 分享链接。"""

    productName: str
    subtitle: str | None = None
    lines: list[str] = []
    qrText: str | None = None
    inviterCode: str | None = None


class ShareTrackIn(CamelModel):
    """分享行为埋点（M8-02 / 1.3 分享率）。"""

    cardId: str | None = None
    channel: str


class BindInviteIn(CamelModel):
    """绑定邀请人（M8-03）。可在注册后单独绑定一次。"""

    inviterCode: str


class ReportCreateIn(CamelModel):
    """生成开业喜报（V5.0 M3-06 / M5-02）。template 为 1—3 的模板编号。"""

    orderId: str | None = None
    template: int = 1


class TalkTopicTrackIn(CamelModel):
    """今日谈资卡转发埋点（V5.0 M5-04）：卡片 id + 渠道。"""

    topicId: str | None = None
    channel: str = "微信好友"


class FunnelTrackIn(CamelModel):
    """转化漏斗埋点（V5.0 M4-07 / M5-04）。

    step：visit / diagnose_start / diagnose_done / pay_click / pay_success / download
    """

    step: str
    source: str | None = None
