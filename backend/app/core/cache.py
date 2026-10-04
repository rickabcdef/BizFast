"""缓存抽象（M2-06 诊断结果 24h 缓存）。

- 生产：Redis（`REDIS_URL` 已配置且 `CACHE_BACKEND=redis|auto`）。
- 本地无 Redis：自动降级为进程内内存缓存（带 TTL），保证本地可完整调试。

对外接口统一为 async：get_json / set_json / get_bytes / set_bytes / delete / exists。
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import settings


class MemoryCache:
    """进程内 TTL 缓存（单进程调试用）。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}

    def _get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expire_at, value = item
        if expire_at and expire_at < time.time():
            self._data.pop(key, None)
            return None
        return value

    async def get_json(self, key: str) -> Any | None:
        raw = self._get(key)
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._data[key] = (time.time() + ttl if ttl else 0.0, json.dumps(value, ensure_ascii=False))

    async def get_bytes(self, key: str) -> bytes | None:
        raw = self._get(key)
        return raw if isinstance(raw, bytes) else None

    async def set_bytes(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self._data[key] = (time.time() + ttl if ttl else 0.0, value)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def exists(self, key: str) -> bool:
        return self._get(key) is not None


class RedisCache:
    """Redis 缓存（生产）。连接不可用时逐键降级为内存缓存。"""

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url, decode_responses=False)
        self._fallback = MemoryCache()

    async def get_json(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(key)
        except Exception:
            return await self._fallback.get_json(key)
        return json.loads(raw) if raw else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        try:
            await self._redis.set(key, payload, ex=ttl)
        except Exception:
            await self._fallback.set_json(key, value, ttl)

    async def get_bytes(self, key: str) -> bytes | None:
        try:
            return await self._redis.get(key)
        except Exception:
            return await self._fallback.get_bytes(key)

    async def set_bytes(self, key: str, value: bytes, ttl: int | None = None) -> None:
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception:
            await self._fallback.set_bytes(key, value, ttl)

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            await self._fallback.delete(key)

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(key))
        except Exception:
            return await self._fallback.exists(key)


_cache = None


def get_cache():
    """返回缓存单例（Redis 不可用时降级为内存缓存）。"""
    global _cache
    if _cache is None:
        if settings.redis_url:
            try:
                _cache = RedisCache(settings.redis_url)
            except Exception:  # pragma: no cover - 环境相关
                _cache = MemoryCache()
        else:
            _cache = MemoryCache()
    return _cache
