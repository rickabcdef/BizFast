"""M10 认证服务：游客创建、手机号登录、JWT 签发/刷新、注销。

实现要点：
- 游客可免登录走完诊断与商机（M1-07），付费前才要求登录（M5）
- 短信验证码开发阶段使用 mock（固定值 123456 或日志输出）
- 注销账号 15 天内清除隐私数据（PRD 3.1）
- 手机号登录自动创建或更新用户记录
"""
from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache
from app.core.config import settings
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models import User


# --------------- 请求体模型 ---------------
class SmsSendBody(BaseModel):
    phone: str

class SmsLoginBody(BaseModel):
    phone: str
    code: str

class PhoneLoginBody(BaseModel):
    """契约路径 POST /api/auth/login 的请求体（手机号 + 验证码 + 可选邀请码）。"""
    phone: str
    code: str
    inviterCode: str | None = None


class WechatLoginBody(BaseModel):
    """契约路径 POST /api/auth/wechat 的请求体（unionid 登录 + 可选邀请码）。

    M0-04：分享卡片 → 微信一键登录是裂变主路径，必须支持携带邀请码绑定邀请关系。
    """

    unionid: str | None = None
    inviterCode: str | None = None


class RefreshBody(BaseModel):
    refresh_token: str


class ProfileUpdateBody(BaseModel):
    """M0-02（V5.0）用户画像：城市 / 资金区间 / 每日时间 / 经验，均可单独更新。

    沿用首屏的点选值，字段 ≤6 个、全部单选或滑块，不强制真实姓名。
    """

    city: str | None = None
    capital_band: str | None = None
    daily_hours_band: str | None = None
    experience: str | None = None


def _generate_invite_code() -> str:
    """生成 8 位唯一邀请码（大写字母+数字）。"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def create_guest(db: AsyncSession) -> dict:
    """创建游客账号。

    - 生成唯一 guest_token
    - 创建 role=guest 的 User 记录
    - 签发 access_token 和 refresh_token
    """
    guest_token = uuid.uuid4().hex
    user_id = str(uuid.uuid4())

    user = User(
        id=user_id,
        guest_token=guest_token,
        role="guest",
        plan="none",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # JWT sub 字段存 user_id
    access_token = create_access_token(sub=user_id)
    refresh_token = create_refresh_token(sub=user_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user_id,
        "is_guest": True,
    }


async def send_sms_code(phone: str) -> dict:
    """发送短信验证码（mock 实现）。

    - 生成 6 位验证码
    - 缓存到 Redis/内存，TTL 5 分钟
    - 生产环境应调用真实短信 API
    """
    cache = get_cache()
    # mock 验证码：开发阶段固定为 123456，方便测试
    code = "123456" if settings.app_env == "development" else "".join(
        random.choices(string.digits, k=6)
    )
    await cache.set(f"sms:code:{phone}", code, ttl=300)  # 5 分钟过期
    # 生产环境这里应调用短信服务商 API
    # TODO: 接入真实短信服务（阿里云短信 / 腾讯云短信）
    return {"message": "验证码已发送", "code": code if settings.app_env == "development" else None}


async def login_with_sms(db: AsyncSession, phone: str, code: str) -> dict:
    """手机号验证码登录。

    - 校验验证码（从缓存读取比对）
    - 查找或创建用户（role 从 guest 升级为 user）
    - 签发 access_token 和 refresh_token
    """
    cache = get_cache()
    cached_code = await cache.get(f"sms:code:{phone}")

    if not cached_code or cached_code != code:
        raise ValueError("验证码错误或已过期")

    # 验证码使用后立即删除
    await cache.delete(f"sms:code:{phone}")

    # 查找或创建用户
    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()

    if user is None:
        # 新用户注册
        user = User(
            id=str(uuid.uuid4()),
            phone=phone,
            role="user",
            plan="none",
            invite_code=_generate_invite_code(),
        )
        db.add(user)
    else:
        # 已有用户：如果是游客，升级为正式用户
        if user.role == "guest":
            user.role = "user"
            user.guest_token = None  # 清除游客标识
            if not user.invite_code:
                user.invite_code = _generate_invite_code()

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(sub=user.id)
    refresh_token = create_refresh_token(sub=user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.id,
        "is_guest": user.role == "guest",
    }


async def login_with_wechat(db: AsyncSession, unionid: str) -> dict:
    """微信 unionid 登录（M10 3.1）。

    网页端没有真实微信 SDK，用占位 unionid 走同一套「查找或创建用户」逻辑，
    保证登录后订单 / 消息归属与手机号登录完全一致（多端权益互通）。

    邀请关系绑定由路由层统一处理（`routers/auth.py::_bind_inviter`），
    与手机号登录共用同一入口，避免两条登录路径行为不一致。
    """
    unionid = (unionid or "").strip()
    if not unionid:
        raise ValueError("缺少微信标识")

    user = (await db.execute(select(User).where(User.unionid == unionid))).scalar_one_or_none()

    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            unionid=unionid,
            role="user",
            plan="none",
            invite_code=_generate_invite_code(),
        )
        db.add(user)
    elif user.role == "guest":
        user.role = "user"
        user.guest_token = None
        if not user.invite_code:
            user.invite_code = _generate_invite_code()

    await db.commit()
    await db.refresh(user)

    return {
        "access_token": create_access_token(sub=user.id),
        "refresh_token": create_refresh_token(sub=user.id),
        "user_id": user.id,
        "is_guest": user.role == "guest",
    }


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    """刷新 access_token。

    - 校验 refresh_token 类型和有效期
    - 查找用户（确保未被删除）
    - 签发新的 access_token
    """
    user_id = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    if user is None:
        raise ValueError("用户不存在或已被删除")
    if user.deleted_at is not None:
        raise ValueError("账号已注销")

    new_access_token = create_access_token(sub=user_id)

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,  # 返回原 refresh_token
        "user_id": user_id,
        "is_guest": user.role == "guest",
    }


async def get_user_profile(db: AsyncSession, user_id: str) -> dict:
    """获取用户信息（含 M0-02 画像 与 M0-03 会员额度）。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    profile = {
        "user_id": user.id,
        "phone": user.phone,
        "unionid": user.unionid,
        "role": user.role,
        "plan": user.plan,
        "plan_expire_at": user.plan_expire_at.isoformat() if user.plan_expire_at else None,
        "auto_renew": user.auto_renew,
        "invite_code": user.invite_code,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        # ---- M0-02（V5.0）用户画像：≤6 个字段，全部来自首屏单选 / 滑块 ----
        "city": user.city,
        "capital_band": user.capital_band,
        "daily_hours_band": user.daily_hours_band,
        "experience": user.experience,
    }

    # ---- M0-03（V5.0）会员额度：已购次数 / 已用启动包数 / 额度剩余 ----
    try:
        from app.services import payment as payment_service

        profile.update(await payment_service.membership_quota(db, user))
    except Exception:  # 额度统计失败不影响资料读取
        pass
    return profile


# ---------------------------------------------------------------- M0-02 用户画像（V5.0）
def _capital_band(capital: int) -> str:
    if capital < 30000:
        return "3 万以内"
    if capital < 100000:
        return "3–10 万"
    if capital < 300000:
        return "10–30 万"
    return "30 万以上"


def _clean_city(city: str | None) -> str | None:
    """画像城市入库前统一归一化：与诊断链路保持一致（「上海市」→「上海」）。

    不在城市库中的输入保留用户原值，避免把合法输入误清空。
    """
    raw = (city or "").strip()[:32]
    if not raw:
        return None
    from app.data.cities import normalize_city

    return (normalize_city(raw) or raw)[:32]


def _hours_band(hours: int) -> str:
    if hours <= 2:
        return "2 小时以内"
    if hours <= 4:
        return "2–4 小时"
    if hours <= 8:
        return "4–8 小时"
    return "8 小时以上"


def _load_json(raw):
    import json

    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


async def sync_profile_from_task(db: AsyncSession, user: User, guest_token: str | None = None) -> bool:
    """M0-02（V5.0）：把用户最近一次诊断的条件回写成用户画像。

    PRD 要求在注册 / 付费时采集「所在城市 / 启动资金区间 / 可投入时间 / 是否有经验」。
    这四个字段用户在首屏已经选过一次 —— 不重复问，直接落库。
    只填空字段，不覆盖用户后来手动修改过的值。
    """
    from app.models import DiagnosisTask

    conds = [DiagnosisTask.user_id == user.id]
    if guest_token or user.guest_token:
        conds.append(DiagnosisTask.guest_token == (guest_token or user.guest_token))
    task = (
        await db.execute(
            select(DiagnosisTask)
            .where(or_(*conds))
            .order_by(DiagnosisTask.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if task is None:
        return False

    changed = False
    if not user.city and task.city:
        user.city = task.city[:32]
        changed = True
    if not user.capital_band and task.capital:
        user.capital_band = _capital_band(int(task.capital))
        changed = True
    if not user.daily_hours_band and task.daily_hours:
        user.daily_hours_band = _hours_band(int(task.daily_hours))
        changed = True
    if not user.experience:
        exp = _load_json(task.extra).get("experience")
        if exp:
            # task.extra 里存的是 none/some/pro 编码，画像对外展示要落成中文文案
            from app.services.diagnose import EXPERIENCE_LABELS

            user.experience = EXPERIENCE_LABELS.get(str(exp), str(exp))[:24]
            changed = True

    if changed:
        await db.commit()
    return changed


async def update_profile(db: AsyncSession, user_id: str, body: "ProfileUpdateBody") -> dict:
    """M0-02（V5.0）：更新用户画像（全部单选 / 滑块，不强制真实姓名）。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    if body.city is not None:
        user.city = _clean_city(body.city)
    if body.capital_band is not None:
        user.capital_band = (body.capital_band or "").strip()[:24] or None
    if body.daily_hours_band is not None:
        user.daily_hours_band = (body.daily_hours_band or "").strip()[:24] or None
    if body.experience is not None:
        user.experience = (body.experience or "").strip()[:24] or None

    await db.commit()
    return await get_user_profile(db, user_id)


async def delete_account(db: AsyncSession, user_id: str) -> dict:
    """注销账号（M10-08）。

    - 标记 deleted_at 和 purge_at（15 天后）
    - 定时任务到 purge_at 时物理清除隐私数据
    - 立即清除登录态（清除 token、游客标识）
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ValueError("用户不存在")

    now = datetime.now(timezone.utc)
    user.deleted_at = now
    user.purge_at = now + timedelta(days=15)
    # 清除登录态
    user.guest_token = None
    user.phone = None
    user.unionid = None

    await db.commit()

    return {
        "user_id": user_id,
        "purge_at": user.purge_at.isoformat(),
        "message": "账号已注销，15 天内将清除所有隐私数据",
    }
