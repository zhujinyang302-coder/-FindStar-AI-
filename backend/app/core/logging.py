"""结构化日志。

每条日志包含 trace 标识（request_id）、logger、级别与消息；
错误日志可携带 route/method/status_code/duration_ms/error_category。
严禁在日志中记录密码、Token、完整私密核验信息或 API Key。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from typing import Any

# 请求追踪标识（由中间件设置），默认 "-"
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# 允许出现在日志中的结构化字段（白名单，避免意外泄露）
_EXTRA_FIELDS = (
    "route",
    "method",
    "status_code",
    "duration_ms",
    "error_category",
    "user_id",
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """输出单行 JSON，便于日志系统采集与检索。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # 降低第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)