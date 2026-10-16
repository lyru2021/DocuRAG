"""
验证任务恢复扫描、异常任务处理与 Celery 派发行为。
"""

from unittest.mock import Mock

from sqlalchemy import func, text, update

from app.models.processing_job import ProcessingJob
from app.services.job_recovery_service import JobRecoveryService
from app.services.processing_job_repository import (
    ProcessingJobRepository,
)


def expire_lease(db_session, task_id: str):
    """将测试任务租约设为过去，避免真实等待。"""

    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == task_id)
        .values(
            lease_expires_at=func.now()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()


def test_pending_job_is_dispatched(db_session, sample_document):
    """pending 任务应被尝试派发。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    dispatch = Mock()
    service = JobRecoveryService(db_session, dispatch)

    result = service.recover_once()

    assert result["dispatched"] == 1
    dispatch.assert_called_once_with(job.task_id)


def test_expired_job_is_recovered_and_dispatched(
    db_session,
    sample_document,
):
    """租约过期且仍可重试的任务应恢复并重新派发。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None
    expire_lease(db_session, job.task_id)

    dispatch = Mock()
    service = JobRecoveryService(db_session, dispatch)

    result = service.recover_once()

    assert result["recovered"] == 1
    assert result["dispatched"] == 1

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "pending"


def test_expired_job_with_exhausted_attempts_fails(
    db_session,
    sample_document,
):
    """执行次数耗尽的过期任务必须终止。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(
        sample_document.id,
        max_attempts=1,
    )
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None
    expire_lease(db_session, job.task_id)

    dispatch = Mock()
    service = JobRecoveryService(db_session, dispatch)

    result = service.recover_once()

    assert result["failed"] == 1
    assert result["dispatched"] == 0
    dispatch.assert_not_called()

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "failed"


def test_dispatch_failure_keeps_pending(
    db_session,
    sample_document,
):
    """Redis 派发失败时，任务保留 pending 以便以后恢复。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    dispatch = Mock(side_effect=ConnectionError("Redis offline"))
    service = JobRecoveryService(db_session, dispatch)

    result = service.recover_once()

    assert result["dispatch_errors"] == 1

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "pending"


def test_recovery_does_not_dispatch_twice(
    db_session,
    sample_document,
):
    """同一任务在派发预留窗口内不会被重复派发。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    dispatch = Mock()
    service = JobRecoveryService(db_session, dispatch)

    first = service.recover_once()
    second = service.recover_once()

    assert first["dispatched"] == 1
    assert second["dispatched"] == 0
    dispatch.assert_called_once_with(job.task_id)


def test_recovery_respects_future_dispatch_time(
    db_session,
    sample_document,
):
    """任务未到计划派发时间时，不得提前执行。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    # 模拟任务已经安排未来五分钟后重试。
    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            next_dispatch_at=func.now()
            + text("INTERVAL '5 minutes'")
        )
    )
    db_session.commit()

    dispatch = Mock()
    service = JobRecoveryService(db_session, dispatch)

    result = service.recover_once()

    assert result["dispatched"] == 0
    dispatch.assert_not_called()

