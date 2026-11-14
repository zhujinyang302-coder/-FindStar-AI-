"""统一响应结构与异常处理。

成功：{"code":0,"message":"success","data":{...},"request_id":"..."}
失败：{"code":"VALIDATION_ERROR","message":"...","details":[...],"request_id":"..."}

错误响应不得包含 SQL、堆栈、密钥、内部网络地址或模型供应商敏感响应头。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)

# 业务错误码（错误类型 -> 对外 code），供服务层在 BusinessError 上覆写使用。
ERROR_CODES: dict[str, str] = {
    "admin_not_allowed": "ADMIN_NOT_ALLOWED",
    "match_not_allowed": "MATCH_NOT_ALLOWED",
    "match_result_gone": "MATCH_RESULT_GONE",
    "match_rate_limited": "MATCH_RATE_LIMITED",
    "view_rate_limited": "VIEW_RATE_LIMITED",
    "contact_rate_limited": "CONTACT_RATE_LIMITED",
    "contact_cooldown": "CONTACT_COOLDOWN",
    "insufficient_info": "INSUFFICIENT_INFO",
    "notice_not_accepted": "NOTICE_NOT_ACCEPTED",
    "invalid_image_key": "INVALID_IMAGE_KEY",
    "invalid_verification": "INVALID_VERIFICATION",
    "contact_info_forbidden": "CONTACT_INFO_FORBIDDEN",
    "request_type_mismatch": "REQUEST_TYPE_MISMATCH",
    "self_request_forbidden": "SELF_REQUEST_FORBIDDEN",
    "duplicate_submission": "DUPLICATE_SUBMISSION",
    "concurrent_confirm": "CONCURRENT_CONFIRM",
    "request_already_handled": "REQUEST_ALREADY_HANDLED",
    "item_not_editable": "ITEM_NOT_EDITABLE",
    "ticket_conflict": "TICKET_CONFLICT",
}


class BusinessError(Exception):
    """业务异常基类，携带对外错误码、消息与 HTTP 状态码。"""

    code: str = "BUSINESS_ERROR"
    status_code: int = 400
    message: str = "请求处理失败"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[Any] | dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class UnauthorizedError(BusinessError):
    code = "UNAUTHORIZED"
    status_code = 401
    message = "请先登录"


class ForbiddenError(BusinessError):
    code = "FORBIDDEN"
    status_code = 403
    message = "无权执行该操作"


class NotFoundError(BusinessError):
    code = "NOT_FOUND"
    status_code = 404
    message = "资源不存在"


class ConflictError(BusinessError):
    code = "CONFLICT"
    status_code = 409
    message = "操作冲突"


class ValidationError(BusinessError):
    code = "VALIDATION_ERROR"
    status_code = 422
    message = "请检查输入字段"


class PayloadTooLargeError(BusinessError):
    code = "PAYLOAD_TOO_LARGE"
    status_code = 413
    message = "文件过大"


class UnsupportedMediaTypeError(BusinessError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    status_code = 415
    message = "文件类型不支持"


class RateLimitError(BusinessError):
    code = "RATE_LIMIT_EXCEEDED"
    status_code = 429
    message = "请求过于频繁，请稍后再试"


class GoneError(BusinessError):
    """410：流程已变更，旧入口不再提供能力。"""

    code = "FLOW_CHANGED"
    status_code = 410
    message = "该功能已下线，请使用新的操作路径"


class ServiceUnavailableError(BusinessError):
    code = "SERVICE_UNAVAILABLE"
    status_code = 503
    message = "服务暂时不可用，请稍后重试"


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", request_id_var.get())


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    """成功响应体（配合 JSONResponse 的默认包装更简洁，此处保留显式构造）。"""
    return {"code": 0, "message": message, "data": data}


def error_body(
    code: str | int, message: str, request_id: str, details: Any = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business_error(request: Request, exc: BusinessError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "business error",
                extra={"route": request.url.path, "error_category": exc.code},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, _request_id(request), exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "message": err.get("msg", "字段不合法"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR", "请检查输入字段", _request_id(request), details
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code_map = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}
        code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message, _request_id(request)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled exception",
            extra={"route": request.url.path, "error_category": "INTERNAL_ERROR"},
        )
        return JSONResponse(
            status_code=500,
            content=error_body(
                "INTERNAL_ERROR", "服务内部错误，请稍后重试", _request_id(request)
            ),
        )