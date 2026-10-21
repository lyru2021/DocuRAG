
"""验证请求 ID 传播与 HTTP 日志中间件。"""

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.request_logging import RequestLoggingMiddleware


def make_test_app() -> FastAPI:
    """建立不依赖数据库的最小测试应用。"""

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health")
    def health():
        """返回测试用健康状态。"""

        return {"status": "ok"}

    return app


def test_request_id_is_generated():
    """缺少请求 ID 时自动生成。"""

    with TestClient(make_test_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_valid_request_id_is_preserved():
    """合法请求 ID 应传播到响应头。"""

    with TestClient(make_test_app()) as client:
        response = client.get(
            "/health",
            headers={"X-Request-ID": "test-request-123"},
        )

    assert response.headers["X-Request-ID"] == "test-request-123"


def test_invalid_request_id_is_replaced():
    """异常或过长的请求 ID 应被替换。"""

    with TestClient(make_test_app()) as client:
        response = client.get(
            "/health",
            headers={"X-Request-ID": "invalid id with spaces"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != (
        "invalid id with spaces"
    )


def test_http_log_contains_request_metadata(caplog):
    """HTTP 日志应包含关联 ID、状态码和耗时。"""

    with caplog.at_level(logging.INFO, logger="docurag.http"):
        with TestClient(make_test_app()) as client:
            response = client.get(
                "/health",
                headers={"X-Request-ID": "audit-123"},
            )

    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "docurag.http"
    ]

    assert records
    entry = records[-1]

    assert entry["request_id"] == "audit-123"
    assert entry["method"] == "GET"
    assert entry["path"] == "/health"
    assert entry["status_code"] == 200
    assert entry["duration_ms"] >= 0
    assert response.status_code == 200
