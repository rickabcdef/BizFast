"""统一错误体系：所有异常归一为中文 message + 重试建议（ADR-006）。

禁止英文报错或裸错误码直出前端。前端展示 message，必要时根据 code 显示重试按钮。
"""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 错误码 → 中文提示（与 frontend/src/types/index.ts 保持一致）
ERROR_MESSAGES: dict[int, str] = {
    0: "ok",
    40001: "请输入启动资金、每日时间和所在城市",
    40002: "当前城市暂不支持，请手动选择",
    40101: "登录已过期，请重新登录",
    40301: "该内容仅付费用户可生成",
    40401: "未找到对应的生意启动包",
    40901: "订单正在生成中，请稍候",
    42901: "操作过于频繁，请稍后再试",
    50001: "服务开小差了，请重试",
    50002: "AI 服务暂时不可用，已切换备用模型",
    60001: "支付未成功，请重新支付",
}


class BizError(Exception):
    """业务异常：携带 code（见 ERROR_MESSAGES）。"""

    def __init__(self, code: int, message: str | None = None):
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, ERROR_MESSAGES[50001])
        super().__init__(self.message)


# 字段名 → 中文名（参数校验失败时拼出「缺什么」的中文提示，避免直出英文 loc）
_FIELD_LABELS: dict[str, str] = {
    "capital": "启动资金",
    "dailyHours": "每日可投入时间",
    "daily_hours": "每日可投入时间",
    "city": "所在城市",
    "taskId": "诊断任务",
    "task_id": "诊断任务",
    "phone": "手机号",
    "code": "验证码",
    "refresh_token": "刷新令牌",
    "username": "账号",
    "password": "密码",
    "totp": "动态验证码",
    "plan": "购买方案",
    "orderId": "订单号",
    "order_id": "订单号",
    "action": "操作类型",
    "reason": "原因",
    "ids": "内容编号",
    "perms": "权限项",
    "version": "版本号",
    "content": "内容",
    "on_shelf": "上下架状态",
    "enabled": "启用状态",
    "items": "导入数据",
    "category": "文案类别",
    "keywords": "关键词",
    "file": "文件",
    "files": "文件列表",
    "pages": "拆分页码",
    "game_type": "游戏类型",
    "score": "分数",
    "inviterCode": "邀请码",
    "channel": "渠道",
    "productName": "产品名称",
}


def _field_label(loc: tuple) -> str:
    """把 FastAPI 校验错误的 loc 转成中文可读字段名。"""
    for part in reversed(loc):
        if isinstance(part, str) and not part.isdigit():
            return _FIELD_LABELS.get(part, part)
    return "参数"


def _validation_message(exc: RequestValidationError) -> str:
    """把 422 校验错误翻译成纯中文提示（ADR-006：禁止英文与裸错误码）。"""
    errors = exc.errors() or []
    if not errors:
        return "提交的参数有误，请检查后重试"
    first = errors[0]
    loc = tuple(first.get("loc") or ())
    label = _field_label(loc)
    etype = first.get("type", "")
    if etype == "missing":
        return f"请填写{label}"
    if etype in ("int_parsing", "float_parsing", "decimal_parsing"):
        return f"{label}格式不正确，请填写数字"
    if etype in ("bool_parsing", "bool_type"):
        return f"{label}格式不正确，请选择是或否"
    if etype in ("string_type", "str_type"):
        return f"{label}格式不正确，请填写文本"
    if etype.startswith("list") or etype in ("tuple_type",):
        return f"{label}格式不正确，请提交列表"
    if etype in ("greater_than_equal", "greater_than", "less_than_equal", "less_than"):
        return f"{label}超出允许范围，请调整后重试"
    if etype in ("value_error", "enum", "literal_error"):
        return f"{label}填写不正确，请重新选择"
    return f"{label}填写不正确，请检查后重试"


def _payload(code: int, message: str, request_id: str | None = None) -> dict:
    return {"code": code, "message": message, "data": None, "request_id": request_id or ""}


def _rid(request: Request | None) -> str:
    """错误响应也回填 request_id，便于按一次调用串联前后端日志。"""
    return getattr(getattr(request, "state", None), "request_id", "") or ""


async def biz_exception_handler(request: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(status_code=200, content=_payload(exc.code, exc.message, _rid(request)))


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 参数校验失败 → 统一中文提示，不暴露英文细节
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=200, content=_payload(40001, _validation_message(exc), _rid(request))
        )
    # 其余未捕获异常 → 50001（内部错误已记录日志）
    return JSONResponse(status_code=200, content=_payload(50001, ERROR_MESSAGES[50001], _rid(request)))
