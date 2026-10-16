"""验证 Celery 文件清理任务的注册和服务调用。"""

from unittest.mock import patch

from app.worker.celery_app import celery_app
from app.worker.file_cleanup_tasks import cleanup_files_task


def test_cleanup_task_is_registered():
    """文件清理任务应具有正确的 Celery 名称。"""

    assert cleanup_files_task.name == "docurag.cleanup_files"
    assert "docurag.cleanup_files" in celery_app.tasks


def test_cleanup_task_calls_service():
    """Celery 任务应调用文件清理服务。"""

    expected = {
        "scanned": 0,
        "completed": 0,
        "errors": 0,
    }

    with patch(
        "app.worker.file_cleanup_tasks.FileCleanupService"
    ) as service_class:
        service_class.return_value.cleanup_once.return_value = expected

        result = cleanup_files_task()

    assert result == expected

    service_class.return_value.cleanup_once.assert_called_once_with(
        limit=100
    )