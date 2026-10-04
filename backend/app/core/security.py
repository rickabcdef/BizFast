"""鉴权：JWT 签发/校验、密码哈希、当前用户依赖。

游客可免登录；注册用户用手机号/微信 unionid；多端权益互通。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import Base, get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def _create_token(sub: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str) -> str:
    return _create_token(sub, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(sub: str) -> str:
    return _create_token(sub, REFRESH_TOKEN_TYPE, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str) -> str:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise JWTError("wrong token type")
        return payload["sub"]
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="40101") from exc


async def get_current_user(
    authorization: Optional[str], db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    sub = decode_token(token, ACCESS_TOKEN_TYPE)
    user = (await db.execute(select(User).where(User.id == sub))).scalar_one_or_none()
    return user
