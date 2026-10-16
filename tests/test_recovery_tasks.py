"""验证 Celery 恢复任务能调用数据库恢复服务。"""

from unittest.mock import patch

from app.worker.recovery_tasks import recover_jobs_task


def test_recover_jobs_task_calls_service():
    """定时恢复任务应调用恢复服务。"""
    expected = {
        "scanned": 0,
        "recovered": 0,
        "failed": 0,
        "dispatched": 0,
        "dispatch_errors": 0,
    }

    with patch(
        "app.worker.recovery_tasks.JobRecoveryService"
    ) as service_class:
        service_class.return_value.recover_once.return_value = expected

        result = recover_jobs_task()

    assert result == expected
    service_class.return_value.recover_once.assert_called_once_with(
        limit=100
    )