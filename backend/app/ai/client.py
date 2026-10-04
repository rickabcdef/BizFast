"""大模型客户端 + 自动降级（M2-08）。

- 主模型不可用时自动切换备用模型，保证单模型故障可用性 ≥99%。
- 不存储用户输入原文（合规红线）。
- 调用失败统一抛 BizError(50002)。
"""
from app.core.config import settings
from app.core.errors import BizError


def _complete(base: str, key: str, model: str, prompt: str) -> str:
    # TODO: 用 httpx 调用 OpenAI 兼容接口；此处为占位实现
    raise NotImplementedError("ai client not wired yet")


def complete(prompt: str) -> str:
    """优先主模型，失败降级备用模型。"""
    try:
        return _complete(
            settings.ai_primary_base, settings.ai_primary_key, settings.ai_primary_model, prompt
        )
    except Exception:
        try:
            return _complete(
                settings.ai_backup_base, settings.ai_backup_key, settings.ai_backup_model, prompt
            )
        except Exception as exc:  # 双模型均失败
            raise BizError(50002) from exc
