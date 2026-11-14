"""请求上下文与统一响应中间件。

- RequestContextMiddleware：生成 trace 标识、记录结构化访问日志。
- UnifiedResponseMiddleware：将成功（<400）的 JSON 响应包装为统一结构
  {"code":0,"message":"success","data":...,"request_id":"..."}。
  探针路径与二进制响应（图片代理）不包装；错误响应由异常处理器统一格式化。
"""

from __future__ import annotations

import json
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, request_id_var

logger = get_logger("app.access")

_SILENT_PATHS = {"/health/live"}
_SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            if request.url.path not in _SILENT_PATHS:
                logger.info(
                    "request",
                    extra={
                        "route": request.url.path,
                        "method": request.method,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )
            request_id_var.reset(token)


class UnifiedResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if not self._should_wrap(request, response):
            return response
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk
        try:
            data = json.loads(body) if body else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return response
        payload = {
            "code": 0,
            "message": "success",
            "data": data,
            "request_id": getattr(request.state, "request_id", request_id_var.get()),
        }
        new_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-length", "content-type"}
        }
        headers["content-type"] = "application/json; charset=utf-8"
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=headers,
        )

    @staticmethod
    def _should_wrap(request: Request, response: Response) -> bool:
        if response.status_code >= 400:
            return False
        if request.url.path.startswith(_SKIP_PREFIXES):
            return False
        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type