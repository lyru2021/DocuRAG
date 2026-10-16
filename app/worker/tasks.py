"""
定义 Celery 后台任务，负责异步执行论文解析与处理。
"""
from app.worker.celery_app import celery_app


@celery_app.task(name="docurag.ping")
def ping_task():
    return {"message": "worker alive"}
