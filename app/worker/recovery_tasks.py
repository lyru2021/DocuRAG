"""
通过 Celery 定期恢复异常中断或等待派发的论文任务。
"""

from app.db.session import SessionLocal
from app.services.job_recovery_service import JobRecoveryService
from app.worker.celery_app import celery_app
from app.worker.paper_tasks import process_paper_task


def dispatch_paper(task_id: str) -> None:
    """向 Celery 派发论文处理任务。"""
    process_paper_task.apply_async(
        args=[task_id],
        task_id=task_id,
    )


@celery_app.task(name="docurag.recover_jobs")
def recover_jobs_task() -> dict:
    """执行一轮任务恢复扫描。"""
    with SessionLocal() as db:
        service = JobRecoveryService(
            db=db,
            dispatch_task=dispatch_paper,
        )
        return service.recover_once(limit=100)