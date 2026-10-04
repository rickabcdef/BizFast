"""Schema 公共基类与统一响应体（见 docs/api-contract.md 1.1）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """请求/响应基类：对外统一 camelCase，内部保持 snake_case。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


def camelize(value: Any) -> Any:
    """把 service 层的 snake_case 输出递归转成契约要求的 camelCase。

    服务层保持 Python 风格的 snake_case，出口统一在 `ok()` 转换，
    避免每个 service 都手写 camelCase（也避免漏改）。
    注意：仅用于**固定的字段名**；接口返回中不含「以业务 id 作键」的字典，
    因此不会误改数据键。
    """
    if isinstance(value, dict):
        return {
            (to_camel(key) if isinstance(key, str) else key): camelize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [camelize(item) for item in value]
    return value


def ok(data: Any = None, request_id: str = "") -> dict:
    """统一成功响应：{code:0, message:'ok', data, request_id}。

    信封自身保持契约原样（`request_id` 为 snake_case），仅 `data` 转 camelCase。
    """
    return {"code": 0, "message": "ok", "data": camelize(data), "request_id": request_id}
