"""
定义论文处理错误类型，并判断异常是否允许自动重试。
"""

from sqlalchemy.exc import DBAPIError, OperationalError


class PermanentProcessingError(Exception):
    """表示无法通过重试解决的论文处理错误。"""


class TransientProcessingError(Exception):
    """表示可能通过重试恢复的临时错误。"""


def is_retryable_error(exc: Exception) -> bool:
    """仅将明确识别的临时错误判定为可重试。"""

    return isinstance(
        exc,
        (
            TransientProcessingError,
            OperationalError,
        ),
    ) or (
        isinstance(exc, DBAPIError)
        and bool(exc.connection_invalidated)
    )


def retry_delay(attempt_count: int) -> int:
    """根据已执行次数计算指数退避时间，单位为秒。"""

    if attempt_count < 1:
        raise ValueError("attempt_count must be >= 1")

    return min(2 ** attempt_count, 60)
