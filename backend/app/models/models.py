"""核心实体（SQLAlchemy 2 风格）。详见 docs/data-model.md。"""
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


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
