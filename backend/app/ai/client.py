"""大模型客户端 + 自动降级（M2-08）。

- 主模型不可用时自动切换备用模型，保证单模型故障可用性 ≥99%。
- 未配置任何模型 / 双模型均失败时，抛 BizError(50002)，由业务层切换到本地规则引擎，
  诊断流程不中断（M2-08 验收：单模型故障时服务可用性 ≥99%）。
- 不存储用户输入原文（合规红线）。
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.core.errors import BizError

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0


def _call(base: str, key: str, model: str, prompt: str) -> str:
    """调用 OpenAI 兼容 /chat/completions 接口。"""
    if not base or not key or not model:
        raise RuntimeError("ai provider not configured")
    import httpx

    url = f"{base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def ai_configured() -> bool:
    """是否配置了至少一个模型。"""
    return bool(
        (settings.ai_primary_base and settings.ai_primary_key and settings.ai_primary_model)
        or (settings.ai_backup_base and settings.ai_backup_key and settings.ai_backup_model)
    )


def complete(prompt: str) -> str:
    """优先主模型，失败降级备用模型；全失败抛 BizError(50002)。"""
    text, degraded = try_complete(prompt)
    if text is None:
        raise BizError(50002)
    return text


def try_complete(prompt: str) -> tuple[str | None, bool]:
    """返回 (文本, 是否降级)。

    文本为 None 表示当前没有任何可用模型（调用方应使用本地规则引擎兜底）。
    """
    if settings.diagnose_mock_ai or not ai_configured():
        return None, True

    primary_ok = bool(
        settings.ai_primary_base and settings.ai_primary_key and settings.ai_primary_model
    )
    if primary_ok:
        try:
            return (
                _call(
                    settings.ai_primary_base,
                    settings.ai_primary_key,
                    settings.ai_primary_model,
                    prompt,
                ),
                False,
            )
        except Exception as exc:
            logger.warning("主模型调用失败，切换备用模型：%s", exc)

    backup_ok = bool(
        settings.ai_backup_base and settings.ai_backup_key and settings.ai_backup_model
    )
    if backup_ok:
        try:
            return (
                _call(
                    settings.ai_backup_base,
                    settings.ai_backup_key,
                    settings.ai_backup_model,
                    prompt,
                ),
                True,
            )
        except Exception as exc:
            logger.warning("备用模型调用失败，降级本地规则引擎：%s", exc)

    return None, True
