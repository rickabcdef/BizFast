"""核心实体（SQLAlchemy 2 风格）。详见 docs/data-model.md。"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("user_id", "match_id", name="uq_order_user_match"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String(16))  # single/month/year
    amount: Mapped[int] = mapped_column(Integer)  # 单位：分
    platform: Mapped[str] = mapped_column(String(16))  # web/weapp/android/ios/harmony/win/mac
    channel: Mapped[str] = mapped_column(String(16))  # wechat/alipay/apple/huawei
    status: Mapped[str] = mapped_column(String(16), default="pending")
    match_id: Mapped[str | None] = mapped_column(String(36))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="orders")
    package: Mapped["Package"] = relationship(back_populates="order", uselist=False)


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
    __tablename__ = "diagnosis_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    capital: Mapped[int] = mapped_column(Integer)
    daily_hours: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(64))
    tags: Mapped[str | None] = mapped_column(Text)  # JSON
    heatmap_url: Mapped[str | None] = mapped_column(Text)
    cache_key: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ShareCard(Base):
    __tablename__ = "share_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    data: Mapped[str] = mapped_column(Text)  # 脱敏后的卡片数据（JSON）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
