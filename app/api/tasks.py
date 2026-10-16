"""
提供异步论文处理任务的状态查询接口。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.worker.paper_tasks import process_paper_task
from app.db.session import get_db
from app.services.processing_job_repository import (
    ProcessingJobRepository,
)


router = APIRouter(prefix="/tasks", tags=["Tasks"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/{task_id}")
def get_task_status(task_id: str, db: DbDep):
    """返回 PostgreSQL 保存的任务状态，不依赖 Celery Result Backend。"""

    job = ProcessingJobRepository(db).get_by_task_id(task_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return {
        "task_id": job.task_id,
        "document_id": job.document_id,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "error_type": job.error_type,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@router.post("/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_task(task_id: str, db: DbDep):
    """为失败的论文处理任务创建新任务并尝试派发。"""

    jobs = ProcessingJobRepository(db)
    original = jobs.get_by_task_id(task_id)

    if original is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    if original.status != "failed":
        raise HTTPException(
            status_code=409,
            detail="Only failed tasks can be retried",
        )

    try:
        new_job = jobs.create_retry_job(task_id)

        if new_job is None:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Task is no longer retryable",
            )

        new_task_id = new_job.task_id
        document_id = new_job.document_id

        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Document already has an active task",
        )

    # 新任务已提交，再原子预留派发资格。
    reserved = jobs.reserve_dispatch(
        task_id=new_task_id,
        interval_seconds=30,
    )

    if not reserved:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Task created but dispatch not reserved",
                "task_id": new_task_id,
            },
        )

    db.commit()

    try:
        process_paper_task.apply_async(
            args=[new_task_id],
            task_id=new_task_id,
        )
    except Exception:
        # 新任务仍保留 pending，预留窗口到期后由 Beat 恢复派发。
        return {
            "task_id": new_task_id,
            "document_id": document_id,
            "status": "pending",
            "dispatch_status": "deferred",
        }

    return {
        "task_id": new_task_id,
        "document_id": document_id,
        "status": "pending",
        "dispatch_status": "sent",
    }