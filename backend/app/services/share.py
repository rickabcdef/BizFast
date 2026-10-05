"""分享与增长 - 负责人 D - 对应 m8_share / m8-03 邀请 / m8-04 回收 / m11_admin 分享概览

职责：
- M8-01 生成成果分享卡片（落库元数据 + 分享链接，卡片图由前端 canvas 渲染）
- M8-02 分享行为埋点 + 1.3 分享率指标
- M8-03 老邀新：被邀请人注册后双方各得券（实时可见）
- M8-04 按渠道回收分享转化，供运营后台呈现
- M11(D) 分享转化概览接口
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.context import ensure_owner_user, owner_key_for_user
from app.core.errors import BizError
from app.models import (
    Coupon,
    DiagnosisTask,
    InviteRelation,
    Order,
    ShareCard,
    ShareEvent,
    User,
)

_REGISTER_CHANNEL = "direct"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _base_url() -> str:
    return (getattr(settings, "share_base_url", "") or "https://bizfast.app").rstrip("/")


async def _gen_invite_code(db) -> str:
    """生成唯一邀请码（BF- + 5 位 base36）。用户域字段；D 分享模块在此兜底生成。"""
    while True:
        code = "BF-" + uuid.uuid4().hex[:5].upper()
        exists = (
            await db.execute(select(func.count()).select_from(User).where(User.invite_code == code))
        ).scalar_one()
        if not exists:
            return code


async def create_card(db, owner, product_name: str, subtitle: str | None, lines: list[str],
                      qr_text: str | None, inviter_code: str | None) -> dict:
    """M8-01 生成成果分享卡片，返回卡片 id 与带邀请码的分享链接。"""
    user = await ensure_owner_user(db, owner)
    card_id = str(uuid.uuid4())
    data = {
        "product_name": product_name,
        "subtitle": subtitle,
        "lines": lines or [],
        "qr_text": qr_text,
    }
    db.add(
        ShareCard(
            id=card_id,
            user_id=user.id or owner.owner_key,
            data=json.dumps(data, ensure_ascii=False),
        )
    )
    await db.commit()
    # 分享链接携带邀请码，用于新用户注册时归因（M8-03）
    code = user.invite_code
    share_url = f"{_base_url()}/?inviter={code}" if code else f"{_base_url()}/"
    return {"id": card_id, "share_url": share_url}


async def get_card(db, card_id: str) -> dict:
    card = (await db.execute(select(ShareCard).where(ShareCard.id == card_id))).scalar_one_or_none()
    if card is None:
        raise BizError(40401, "分享卡片不存在或已失效")
    data = json.loads(card.data or "{}")
    return {"id": card.id, **data}


async def track_event(db, owner, card_id: str | None, channel: str) -> dict:
    """M8-02 分享行为埋点。"""
    if not channel:
        raise BizError(40001, "分享渠道不能为空")
    db.add(
        ShareEvent(
            owner_key=owner.owner_key,
            card_id=card_id,
            channel=channel,
            event_type="share",
        )
    )
    await db.commit()
    return {"ok": True}


async def bind_invite(db, inviter_code: str | None, invitee_user: User) -> dict:
    """M8-03 绑定邀请人（老邀新）。幂等：已绑定则直接返回。双方各发一张邀请券，实时可见。"""
    code = (inviter_code or "").strip().upper()
    if not code:
        raise BizError(40001, "邀请码不能为空")
    inviter = (
        await db.execute(select(User).where(User.invite_code == code))
    ).scalar_one_or_none()
    if inviter is None:
        raise BizError(40401, "邀请码无效")
    if inviter.id == invitee_user.id:
        raise BizError(40001, "不能填写自己的邀请码")

    existing = (
        await db.execute(
            select(InviteRelation).where(InviteRelation.invitee_user_id == invitee_user.id)
        )
    ).scalar_one_or_none()
    if existing:
        return {"status": existing.status, "already": True}

    rel = InviteRelation(
        id=str(uuid.uuid4()),
        inviter_user_id=inviter.id,
        invitee_user_id=invitee_user.id,
        status="issued",
    )
    db.add(rel)
    await _issue_invite_coupons(db, inviter, invitee_user, rel)
    # 注册归因：用作分享转化的 register 事件（渠道记为 direct）
    db.add(
        ShareEvent(
            owner_key=owner_key_for_user(inviter),
            channel=_REGISTER_CHANNEL,
            event_type="register",
        )
    )
    await db.commit()
    return {"status": "issued", "already": False}


async def _issue_invite_coupons(db, inviter: User, invitee: User, rel: InviteRelation) -> None:
    """双方各得一张 ¥10 邀请券（kind=invite，不与优惠码叠加规则冲突，独立券种）。"""
    inv_code = "INV-" + uuid.uuid4().hex[:6].upper()
    inv_code2 = "INV-" + uuid.uuid4().hex[:6].upper()
    db.add(
        Coupon(
            code=inv_code,
            kind="invite",
            title="邀请好友得 ¥10 券（你）",
            discount_type="amount",
            value=1000,
            plan_scope="",
            min_amount=0,
            total_quota=0,
            per_user_limit=1,
            active=True,
        )
    )
    db.add(
        Coupon(
            code=inv_code2,
            kind="invite",
            title="受邀新人 ¥10 券",
            discount_type="amount",
            value=1000,
            plan_scope="",
            min_amount=0,
            total_quota=0,
            per_user_limit=1,
            active=True,
        )
    )
    rel.coupon_code = inv_code2


async def invite_info(db, owner) -> dict:
    """当前用户的邀请信息（M8-03 实时可见）。"""
    user = await ensure_owner_user(db, owner)
    if not user.invite_code:
        user.invite_code = await _gen_invite_code(db)
        await db.commit()
    code = user.invite_code
    return {
        "code": code,
        "link": f"{_base_url()}/?inviter={code}",
        "coupon": "新人立减 ¥10 券",
        "free_generations": 1,
    }


async def get_share_stats(db) -> dict:
    """M8-04 / M11(D) 分享转化概览：按渠道点击 + 邀请注册/付费汇总 + 分享率。"""
    events = (await db.execute(select(ShareEvent))).scalars().all()
    by_channel: dict[str, int] = {}
    for e in events:
        if e.event_type == "share":
            by_channel[e.channel] = by_channel.get(e.channel, 0) + 1
    rows = [{"channel": c, "clicks": n} for c, n in by_channel.items()]
    rows.sort(key=lambda r: -r["clicks"])

    invites = (await db.execute(select(InviteRelation))).scalars().all()
    registers = len(invites)
    pays = 0
    for inv in invites:
        cnt = (
            await db.execute(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.user_id == inv.invitee_user_id,
                    Order.status.in_(["paid", "generating", "delivered", "refunded"]),
                )
            )
        ).scalar_one()
        pays += cnt

    total_shares = sum(r["clicks"] for r in rows)
    result_cnt = (
        await db.execute(select(func.count()).select_from(DiagnosisTask))
    ).scalar_one() or 0
    share_rate = round(total_shares / result_cnt, 4) if result_cnt else 0.0

    return {
        "rows": rows,
        "summary": {
            "shares": total_shares,
            "registers": registers,
            "pays": pays,
            "share_rate": share_rate,
        },
    }
