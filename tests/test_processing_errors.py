"""
验证论文处理异常分类与指数退避计算规则。
"""

import pytest
from sqlalchemy.exc import OperationalError

from app.services.processing_errors import (
    PermanentProcessingError,
    TransientProcessingError,
    is_retryable_error,
    retry_delay,
)


def test_transient_error_is_retryable():
    """明确的临时错误应该允许重试。"""

    assert is_retryable_error(
        TransientProcessingError("Temporary failure")
    )


def test_operational_error_is_retryable():
    """数据库操作性错误允许进入有限重试流程。"""

    error = OperationalError(
        "SELECT 1",
        {},
        Exception("Connection unavailable"),
    )

    assert is_retryable_error(error)


def test_permanent_error_is_not_retryable():
    """损坏 PDF 等永久错误不允许自动重试。"""

    assert not is_retryable_error(
        PermanentProcessingError("Invalid PDF")
    )


def test_unknown_error_is_not_retryable():
    """未知异常不能默认无限重试。"""

    assert not is_retryable_error(
        RuntimeError("Unexpected failure")
    )


def test_exponential_backoff():
    """重试延迟随执行次数增长，但不会无限增加。"""

    assert retry_delay(1) == 2
    assert retry_delay(2) == 4
    assert retry_delay(3) == 8
    assert retry_delay(10) == 60


def test_invalid_attempt_count():
    """不允许使用无效执行次数计算退避时间。"""

    with pytest.raises(ValueError):
        retry_delay(0)
