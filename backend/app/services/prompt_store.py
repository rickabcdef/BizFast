"""运营后台提示词配置的读取入口（V5.0 M11-04）。

背景（真实存在的缺陷）
--------------------
后台「提示词配置」页面可以新建 / 编辑 / 回滚提示词，并本地「测试」，
但用户端真正调 AI 时用的是代码里硬编码的 prompt（见 diagnose 的 scan 阶段），
后台配置**从来没被读过**——典型的「看得见、不生效」，M11-04 那句
「修改后无需发版即可生效」并未兑现。

本模块让用户端真正读后台配置：

- 后台配置过且内容非空 → 用后台的提示词（支持 ``{city}`` ``{capital}``
  ``{daily_hours}`` 等占位符，由调用方填充）；
- 未配置 / 内容为空 / 文件损坏 → 返回 None，调用方回退代码内置提示词，
  保证「运营没配过」时行为与改动前完全一致。

按文件 mtime 做进程内缓存；后台保存 / 回滚后调 ``refresh()`` 立即重建。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 与 app/services/admin.py 的 CONFIG_DIR 指向同一处（backend/data/admin_config）
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "admin_config" / "prompts.json"

_cache: dict[str, object] = {"mtime": None, "items": None}


def _load() -> list[dict]:
    try:
        if not _CONFIG_PATH.exists():
            return []
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - 配置损坏不应影响用户端
        logger.warning("提示词配置解析失败，回退内置提示词：%s", exc)
        return []
    return data if isinstance(data, list) else []


def _items() -> list[dict]:
    try:
        mtime = _CONFIG_PATH.stat().st_mtime if _CONFIG_PATH.exists() else None
    except OSError:  # pragma: no cover
        mtime = None
    if _cache["items"] is None or _cache["mtime"] != mtime:
        _cache["items"] = _load()
        _cache["mtime"] = mtime
    return _cache["items"]  # type: ignore[return-value]


def get_prompt(key: str) -> str | None:
    """返回后台为该 key 配置的提示词内容；未配置或为空时返回 None。"""
    for item in _items():
        if isinstance(item, dict) and item.get("key") == key:
            content = (item.get("content") or "").strip()
            return content or None
    return None


def render(key: str, variables: dict | None = None) -> str | None:
    """取后台提示词并填充占位符。

    模板里出现未知占位符时**原样返回**——宁可提示词少替换一处，
    也不能因为运营多打了一对花括号就让线上诊断崩掉。
    """
    tpl = get_prompt(key)
    if not tpl:
        return None
    if not variables:
        return tpl
    try:
        return tpl.format(**variables)
    except (KeyError, IndexError, ValueError):
        logger.warning("提示词 %s 存在未知占位符，按原文使用", key)
        return tpl


def refresh() -> None:
    """后台保存 / 回滚提示词后调用，让下一次读取立刻重建。"""
    _cache["items"] = None
    _cache["mtime"] = None
