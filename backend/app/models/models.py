"""核心实体（SQLAlchemy 2 风格）。详见 docs/data-model.md。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    unionid: Mapped[str | None] = mapped_column(String(64), unique=True)
    guest_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="guest")  # guest/user/admin
    plan: Mapped[str] = mapped_column(String(16), default="none")  # none/single/month/year
    plan_expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M5-08 自动续费签约：会员可自助开启/取消，取消入口不超过 3 步
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    renew_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M8-03 邀请：每位用户一个唯一邀请码（注册时生成）
    invite_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    # M10 注销：15 日内清隐私数据（先标记，定时任务到点后物理清除）
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    sent_invites: Mapped[list["InviteRelation"]] = relationship(
        back_populates="inviter", foreign_keys="InviteRelation.inviter_user_id"
    )
    received_invites: Mapped[list["InviteRelation"]] = relationship(
        back_populates="invitee", foreign_keys="InviteRelation.invitee_user_id"
    )


class Order(Base):
    """订单状态机（M5-05）。

    待支付 → 已支付 → 生成中 → 已交付；待支付/已支付/生成中 → 已关闭；
    已支付/生成中/已交付 → 已退款。每态带时间戳。
    """

    __tablename__ = "orders"
    # 同一用户对同一商机只允许存在「一份进行中的订单」（幂等防重复扣款）；
    # 订单已关闭 / 已退款后允许再次购买（M5-07：退款后用户应能重新下单）。
    # 因此使用「部分唯一索引」，只约束进行中的状态，而不是全表唯一。
    __table_args__ = (
        Index(
            "uq_order_user_match_active",
            "user_id",
            "match_id",
            unique=True,
            sqlite_where=text(
                "match_id IS NOT NULL AND status IN "
                "('pending','paid','generating','delivered')"
            ),
            postgresql_where=text(
                "match_id IS NOT NULL AND status IN "
                "('pending','paid','generating','delivered')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String(16))  # single/month/year
    amount: Mapped[int] = mapped_column(Integer)  # 单位：分
    platform: Mapped[str] = mapped_column(String(16))  # web/weapp/android/ios/harmony/win/mac
    channel: Mapped[str] = mapped_column(String(16))  # wechat/alipay/apple/huawei
    status: Mapped[str] = mapped_column(String(16), default="pending")
    match_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    # M5-09 优惠券 / 邀请码：记录核销的码与减免金额（分），便于对账与风控
    coupon_code: Mapped[str | None] = mapped_column(String(32))
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    # M5-10 风控：命中规则时标记需人工审核，不直接放行
    risk_flag: Mapped[str | None] = mapped_column(String(32))
    # 状态时间戳（M5-05：状态流转可追溯，每步有时间戳）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generating_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="orders")
    package: Mapped["Package"] = relationship(back_populates="order", uselist=False)


class PaymentRecord(Base):
    """支付流水 / 回调审计（M5-06 不漏单、可追溯）。"""

    __tablename__ = "payment_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    # create / callback / query / refund / fail
    action: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Package(Base):
    __tablename__ = "packages"
    # 一个订单只允许一个启动包：并发/重复触发时由数据库兜底拒绝第二条记录
    # （M4-01 幂等，避免 Package 重复行导致 scalar_one_or_none 抛 MultipleResultsFound）
    __table_args__ = (UniqueConstraint("order_id", name="uq_packages_order_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="generating")  # generating/delivered/failed
    zip_url: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    order: Mapped["Order"] = relationship(back_populates="package")
    items: Mapped[list["DeliverableFile"]] = relationship(back_populates="package")


class DeliverableFile(Base):
    __tablename__ = "deliverable_files"
    # 同一交付物的同一格式只允许一行（重复生成/并发写入时兜底去重）
    __table_args__ = (
        UniqueConstraint("package_id", "code", "file_type", name="uq_deliverable_pkg_code_fmt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("packages.id"))
    code: Mapped[str] = mapped_column(String(8))  # D01..D10
    name: Mapped[str] = mapped_column(String(128))
    file_type: Mapped[str] = mapped_column(String(8))  # pdf/excel/word/png/svg/txt/zip
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    package: Mapped["Package"] = relationship(back_populates="items")


class DiagnosisTask(Base):
    """诊断任务（M2）。进度来自真实阶段完成情况（M2-02）。"""

    __tablename__ = "diagnosis_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    guest_token: Mapped[str | None] = mapped_column(String(64))
    capital: Mapped[int] = mapped_column(Integer)
    daily_hours: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(64))
    tags: Mapped[str | None] = mapped_column(Text)  # JSON
    result: Mapped[str | None] = mapped_column(Text)  # JSON：热度方向 + 匹配商机 id
    heatmap_key: Mapped[str | None] = mapped_column(String(160))
    heatmap_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/ready/failed
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    percent: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(160), default="正在排队诊断")
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    # M2-07 补充问答（可选，JSON）：经验/经营形态/最在意项；跳过则为 None
    extra: Mapped[str | None] = mapped_column(Text)
    cache_key: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Favorite(Base):
    """商机收藏（M3-06，P1）。"""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("owner_key", "opportunity_id", name="uq_favorite_owner_opp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # owner_key = user_id（登录）或 guest_token（游客），保证游客也能收藏
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Notification(Base):
    """站内消息中心（M9-01）。"""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_owner_created", "owner_key", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    # system/order/activity/package/refund
    category: Mapped[str] = mapped_column(String(16), default="system")
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(200))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ShareEvent(Base):
    """分享行为埋点（M8-02 / 1.3 分享率指标）。

    event_type: share=点击分享；register=被邀请人注册；pay=被邀请人付费。
    channel: 微信好友 / 朋友圈 / 抖音 / 小红书 / 复制链接 / 保存图片 / direct。
    """
    __tablename__ = "share_events"
    __table_args__ = (Index("ix_share_event_channel_created", "channel", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    card_id: Mapped[str | None] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="direct")
    event_type: Mapped[str] = mapped_column(String(16), default="share")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InviteRelation(Base):
    """邀请关系（M8-03 老邀新，双方各得券）。"""
    __tablename__ = "invite_relations"
    __table_args__ = (
        UniqueConstraint("invitee_user_id", name="uq_invite_invitee"),
        Index("ix_invite_inviter", "inviter_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inviter_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    invitee_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    coupon_code: Mapped[str | None] = mapped_column(String(32))
    # pending/issued/done
    status: Mapped[str] = mapped_column(String(16), default="issued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inviter: Mapped["User"] = relationship(back_populates="sent_invites", foreign_keys=[inviter_user_id])
    invitee: Mapped["User"] = relationship(back_populates="received_invites", foreign_keys=[invitee_user_id])


class NotifySetting(Base):
    """消息订阅与免打扰设置（M9-02/03/04/06）。"""

    __tablename__ = "notify_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    service_notice: Mapped[bool] = mapped_column(Boolean, default=True)  # 微信服务通知
    app_push: Mapped[bool] = mapped_column(Boolean, default=True)  # App 系统推送
    desktop_notice: Mapped[bool] = mapped_column(Boolean, default=True)  # 桌面端通知
    market_reminder: Mapped[bool] = mapped_column(Boolean, default=True)  # 商机库更新提醒
    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 免打扰
    dnd_start: Mapped[str] = mapped_column(String(5), default="22:00")
    dnd_end: Mapped[str] = mapped_column(String(5), default="08:00")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ShareCard(Base):
    __tablename__ = "share_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    data: Mapped[str] = mapped_column(Text)  # 脱敏后的卡片数据（JSON）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Coupon(Base):
    """优惠券 / 邀请码（M5-09）。

    规则（PRD 验收）：**优惠券不可叠加使用**，且规则必须在页面/接口明示。
    `kind` 区分券（coupon）与邀请码（invite），两者同样不可叠加。
    """

    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="coupon")  # coupon/invite
    title: Mapped[str] = mapped_column(String(64), default="优惠券")
    # 减免方式：amount=固定金额（分）；percent=按比例（value 为 1–100 的百分比）
    discount_type: Mapped[str] = mapped_column(String(16), default="amount")
    value: Mapped[int] = mapped_column(Integer, default=0)
    # 限定可用的价格档；空字符串表示不限
    plan_scope: Mapped[str] = mapped_column(String(32), default="")
    min_amount: Mapped[int] = mapped_column(Integer, default=0)  # 门槛（分）
    total_quota: Mapped[int] = mapped_column(Integer, default=0)  # 0 = 不限量
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CouponRedemption(Base):
    """券核销流水：同一订单只允许核销一张券（不可叠加）。"""

    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_redemption_order"),
        Index("ix_redemption_owner_code", "owner_key", "code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str] = mapped_column(String(36))
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RiskEvent(Base):
    """风控事件（M5-10）：防刷单 / 防恶意退款 / 防批量注册薅羊毛。

    记录异常行为，必要时标记人工审核；不做静默放行，也不粗暴拒绝。
    """

    __tablename__ = "risk_events"
    __table_args__ = (Index("ix_risk_owner_created", "owner_key", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    signal: Mapped[str] = mapped_column(String(64), index=True)  # 命中的规则标识
    # normal / review（需人工审核）/ blocked
    level: Mapped[str] = mapped_column(String(16), default="normal")
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GameScore(Base):
    """M7 小游戏分数记录。

    游戏类型：match3（消消乐）、2048（数字合并）。
    支持游客和登录用户，游客分数通过 owner_key 关联。
    """

    __tablename__ = "game_scores"
    __table_args__ = (
        Index("ix_game_score_user_type", "user_id", "game_type"),
        Index("ix_game_score_type_score", "game_type", "score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    game_type: Mapped[str] = mapped_column(String(16))  # match3/2048
    score: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    extra_data: Mapped[str | None] = mapped_column(Text)  # JSON：关卡数等
    is_personal_best: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ============================================================ V5.0 新增


class AiCostLog(Base):
    """V5.0 第 7 章 AI 成本记账（支撑 M4-05 成本监控看板与 25% 告警）。

    每一笔 AI 调用落一条流水：Token 消耗 + 折算成本（分）。
    `template_mode` 标记是否走了模板降级（预算熔断），`cache_hit` 标记缓存命中，
    用于核算「六道闸门」的实际节流效果。
    """

    __tablename__ = "ai_cost_logs"
    __table_args__ = (
        Index("ix_ai_cost_feature_created", "feature", "created_at"),
        Index("ix_ai_cost_owner_created", "owner_key", "created_at"),
        Index("ix_ai_cost_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_key: Mapped[str | None] = mapped_column(String(64), index=True)
    order_id: Mapped[str | None] = mapped_column(String(36))
    # 功能位：diagnose（诊断）/ package（启动包）/ coach（AI 教练）/ poster（海报）/ report（喜报）…
    feature: Mapped[str] = mapped_column(String(32), default="diagnose")
    model: Mapped[str] = mapped_column(String(64), default="")
    tier: Mapped[str] = mapped_column(String(8), default="light")  # light/mid/top
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)  # 折算成本（分）
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    template_mode: Mapped[bool] = mapped_column(Boolean, default=False)  # 熔断降级到模板模式
    rounds: Mapped[int] = mapped_column(Integer, default=0)  # 本次消耗轮数（轮数上限闸门）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TalkTopic(Base):
    """V5.0 M5-03 今日谈资卡（免费传播物）。

    每天一条「同城/本行业赚钱机会速览」，模板化生成（单次成本 ≤ 0.03 元），
    卡片不带付费引导，只带品牌标识与来源日期，支持一键转发。
    """

    __tablename__ = "talk_topics"
    __table_args__ = (UniqueConstraint("topic_date", "city", name="uq_talk_topic_date_city"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    city: Mapped[str] = mapped_column(String(32), default="全国")
    industry: Mapped[str] = mapped_column(String(32), default="综合")
    title: Mapped[str] = mapped_column(String(128), default="")
    lines: Mapped[str] = mapped_column(Text, default="[]")  # JSON：卡片要点（3—5 条）
    content: Mapped[str] = mapped_column(Text, default="{}")  # JSON：完整渲染内容（版式字段）
    source: Mapped[str] = mapped_column(String(64), default="生意快启商机库")
    cover_text: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ShareReport(Base):
    """V5.0 M3-06 / M5-02 开业喜报（可发朋友圈，≥ 3 种模板）。

    喜报不带硬付费引导，只带品牌标识与 slogan；落库支撑「我的喜报与素材」。
    """

    __tablename__ = "share_reports"
    __table_args__ = (Index("ix_report_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(String(36))
    template: Mapped[int] = mapped_column(Integer, default=1)  # 1/2/3 三种模板
    title: Mapped[str] = mapped_column(String(128), default="")
    subtitle: Mapped[str] = mapped_column(String(128), default="")
    image_url: Mapped[str | None] = mapped_column(Text)
    share_url: Mapped[str | None] = mapped_column(Text)
    data: Mapped[str] = mapped_column(Text, default="{}")  # JSON：喜报文案字段
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DailyReport(Base):
    """V5.0 第 8 章 8.2：每日数据日报（每天 9 点自动生成并推送）。

    内容 = 昨日营收 / 订单 / 新增 / 退款 / AI 成本 / 净现金流。落库后
    后台可查历史，推送失败也不丢数据（先落库、再推送）。
    """

    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("report_date", name="uq_daily_report_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD（统计日）
    revenue_cents: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    refund_cents: Mapped[int] = mapped_column(Integer, default=0)
    refund_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    net_cash_cents: Mapped[int] = mapped_column(Integer, default=0)
    # 推送状态：pending / sent / failed（未配置推送渠道时保持 pending，不阻断日报生成）
    push_status: Mapped[str] = mapped_column(String(12), default="pending")
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content: Mapped[str] = mapped_column(Text, default="")  # 推送给创始人的纯文本日报
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AdminAlert(Base):
    """V5.0 M2-04：后台告警（异常订单 / 成本超限）。

    异常订单出现后 5 分钟内由后台扫描任务写入并推送；用 fingerprint 去重，
    避免同一异常每个扫描周期重复刷屏。
    """

    __tablename__ = "admin_alerts"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_admin_alert_fingerprint"),
        Index("ix_admin_alert_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # order_abnormal / cost_overrun / delivery_failed
    alert_type: Mapped[str] = mapped_column(String(24), index=True)
    level: Mapped[str] = mapped_column(String(8), default="danger")  # danger / warning
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    # 关联对象（订单号等），用于后台一键跳转处理
    related_type: Mapped[str | None] = mapped_column(String(16))
    related_id: Mapped[str | None] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FunnelEvent(Base):
    """V5.0 M4-07 转化漏斗埋点。

    step：visit（访问）→ diagnose_start（开始诊断）→ diagnose_done（完成诊断）
    → pay_click（点击付费）→ pay_success（支付成功）→ download（下载交付物）。
    """

    __tablename__ = "funnel_events"
    __table_args__ = (
        Index("ix_funnel_step_created", "step", "created_at"),
        Index("ix_funnel_owner_created", "owner_key", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_key: Mapped[str | None] = mapped_column(String(64), index=True)
    step: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str | None] = mapped_column(String(32))  # 来源渠道
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
