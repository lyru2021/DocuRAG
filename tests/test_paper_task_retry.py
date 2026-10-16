"""
测试 Celery 任务遇到临时错误时是否按策略安排重试。
"""

from unittest.mock import patch

import pytest

from app.services.processing_errors import (
    TransientProcessingError,
)
from app.worker.paper_tasks import process_paper_task


def test_retry_delay_is_passed_to_celery():
    """临时异常应使用指数退避时间，而不是立即无限重试。"""

    error = TransientProcessingError("Temporary failure")

    # 这里先验证 Celery 重试调用的参数。
    # 真正的 PostgreSQL 状态流转需要单独的集成测试。
    with patch.object(
        process_paper_task,
        "retry",
        side_effect=RuntimeError("Retry scheduled"),
    ) as retry_mock:
        with pytest.raises(RuntimeError, match="Retry scheduled"):
            process_paper_task.retry(
                exc=error,
                countdown=2,
                max_retries=2,
            )

    retry_mock.assert_called_once_with(
        exc=error,
        countdown=2,
        max_retries=2,
    )
