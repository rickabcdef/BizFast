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


def _payload(code: int, message: str, request_id: str | None = None) -> dict:
    return {"code": code, "message": message, "data": None, "request_id": request_id or ""}


async def biz_exception_handler(request: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(status_code=200, content=_payload(exc.code, exc.message))


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 参数校验失败 → 统一中文提示，不暴露英文细节
    if isinstance(exc, RequestValidationError):
        return JSONResponse(status_code=200, content=_payload(40001, ERROR_MESSAGES[40001]))
    # 其余未捕获异常 → 50001（内部错误已记录日志）
    return JSONResponse(status_code=200, content=_payload(50001, ERROR_MESSAGES[50001]))
