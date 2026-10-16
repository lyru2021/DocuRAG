"""通过 Celery 定期执行待处理的本地 PDF 文件清理任务。"""

from app.db.session import SessionLocal
from app.services.file_cleanup_service import FileCleanupService
from app.worker.celery_app import celery_app


@celery_app.task(name="docurag.cleanup_files")
def cleanup_files_task() -> dict:
    """执行一轮持久化文件清理任务。"""

    with SessionLocal() as db:
        service = FileCleanupService(db)
        return service.cleanup_once(limit=100)