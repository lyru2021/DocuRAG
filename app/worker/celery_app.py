"""配置 DocuRAG 的 Celery Worker 与定时任务调度。"""

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "docurag",
    broker=settings.REDIS_URL,
)

celery_app.conf.update(
    # 任务消息使用 JSON 格式。
    task_serializer="json",
    accept_content=["json"],

    timezone="UTC",
    enable_utc=True,
    task_track_started=True,

    # 降低 Worker 预取任务数量，并在任务执行后确认消息。
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    task_default_queue="docurag",

    # 注册全部任务模块。
    imports=(
        "app.worker.tasks",
        "app.worker.paper_tasks",
        "app.worker.recovery_tasks",
        "app.worker.file_cleanup_tasks",
    ),

    # 每 10 秒触发一次数据库任务恢复扫描。
    beat_schedule={
        "recover-processing-jobs": {
            "task": "docurag.recover_jobs",
            "schedule": 10.0,
        },
        "cleanup-original-pdfs": {
            "task": "docurag.cleanup_files",
            "schedule": 30.0,
        },
    },
)