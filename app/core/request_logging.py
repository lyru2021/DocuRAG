"""HTTP 请求追踪与结构化访问日志。"""

import json
import logging
import re
import time
import uuid

from contextvars import ContextVar
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# 使用独立的应用日志，明确输出到 stderr。
# Docker 会收集容器进程的 stdout/stderr。
logger = logging.getLogger("docurag.http")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(message)s")
    )
    logger.addHandler(handler)

# 测试环境中的 caplog 通过根 Logger 捕获日志。
logger.propagate = True

# 当前请求的关联标识，避免并发请求相互覆盖。
request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def normalize_request_id(value: str | None) -> str:
    """接受格式安全的请求 ID，否则生成新的 UUID。"""

    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value

    return uuid.uuid4().hex


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """为 HTTP 请求附加关联标识并记录耗时。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        """记录单次请求，不输出凭据和请求正文。"""

        request_id = normalize_request_id(
            request.headers.get("X-Request-ID")
        )
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round(
                (time.perf_counter() - start) * 1000,
                2,
            )

            try:
                logger.info(
                    json.dumps(
                        {
                            "event": "http_request",
                            "request_id": request_id,
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": status_code,
                            "duration_ms": duration_ms,
                        },
                        ensure_ascii=False,
                    )
                )
            finally:
                # 无论请求成功还是失败，都恢复原来的上下文。
                request_id_context.reset(token)
