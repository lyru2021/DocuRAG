"""
测试论文处理任务的状态转换、幂等性和异常处理。
"""
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.services.processing_job_repository import ProcessingJobRepository


def test_create_pending_job(db_session, sample_document):
    """新任务初始状态必须为 pending。"""
    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    assert job.status == "pending"
    assert job.attempt_count == 0
    assert job.max_attempts == 3


def test_claim_job_only_once(db_session, sample_document):
    """相同任务连续认领两次，只有第一次成功。"""
    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    first = repo.claim_job(job.task_id)
    db_session.commit()

    second = repo.claim_job(job.task_id)
    db_session.commit()

    assert first is not None
    assert first.status == "processing"
    assert first.attempt_count == 1
    assert second is None


def test_mark_completed(db_session, sample_document):
    """有效 Worker 可以完成自己认领的任务。"""
    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    success = repo.mark_completed(
        job.task_id,
        claimed.attempt_count,
    )
    db_session.commit()

    assert success is True

    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "completed"
    assert updated.finished_at is not None


def test_old_attempt_cannot_complete(
    db_session,
    sample_document,
):
    """错误的执行次数不能修改任务状态。"""
    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    success = repo.mark_completed(
        job.task_id,
        attempt_count=999,
    )
    db_session.commit()

    assert success is False

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "processing"


def test_mark_failed_records_error(
    db_session,
    sample_document,
):
    """任务失败时应保存错误类别与简要原因。"""
    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    success = repo.mark_failed(
        job.task_id,
        claimed.attempt_count,
        error_type="InvalidPDFError",
        error_message="PDF content cannot be parsed",
    )
    db_session.commit()

    assert success is True

    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "failed"
    assert updated.error_type == "InvalidPDFError"
    assert updated.finished_at is not None


def test_prepare_retry_returns_job_to_pending(
    db_session,
    sample_document,
):
    """暂时性错误发生后，任务可恢复 pending 状态。"""

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(
        sample_document.id,
        max_attempts=3,
    )
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None
    assert claimed.attempt_count == 1

    success = repo.prepare_retry(
        job.task_id,
        attempt_count=1,
        error_type="OperationalError",
        error_message="Temporary database failure",
    )
    db_session.commit()

    assert success is True

    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "pending"
    assert updated.attempt_count == 1

    # 模拟 Celery 再次投递同一个任务。
    second = repo.claim_job(job.task_id)
    db_session.commit()

    assert second is not None
    assert second.status == "processing"
    assert second.attempt_count == 2



def test_prepare_retry_rejected_when_attempts_exhausted(
    db_session,
    sample_document,
):
    """已达到最大执行次数时，不能重新进入 pending。"""

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(
        sample_document.id,
        max_attempts=1,
    )
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    success = repo.prepare_retry(
        job.task_id,
        attempt_count=1,
        error_type="OperationalError",
        error_message="Database unavailable",
    )
    db_session.commit()

    assert success is False

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "processing"


def test_claim_job_sets_lease(
    db_session,
    sample_document,
):
    """认领任务时应生成租约到期时间。"""

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None
    assert claimed.lease_expires_at is not None


def test_renew_lease_for_current_attempt(
    db_session,
    sample_document,
):
    """只有当前有效执行尝试才能续租。"""

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    assert repo.renew_lease(
        job.task_id,
        claimed.attempt_count,
    ) is True

    assert repo.renew_lease(
        job.task_id,
        attempt_count=999,
    ) is False

    db_session.commit()


def test_recover_expired_job(
    db_session,
    sample_document,
):
    """租约过期的任务可以恢复为 pending。"""

    from sqlalchemy import func, text, update

    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    # 只在测试中将租约改为过去，不需要真实等待十分钟。
    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            lease_expires_at=func.now()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    assert repo.recover_expired_job(job.task_id) is True
    db_session.commit()

    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "pending"
    assert updated.lease_expires_at is None
    assert updated.attempt_count == 1

    # 恢复完成后不能再次恢复。
    assert repo.recover_expired_job(job.task_id) is False

def test_expired_worker_cannot_complete(
    db_session,
    sample_document,
):
    """租约过期后，旧 Worker 不能提交完成状态。"""

    from sqlalchemy import func, text, update
    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()
    assert claimed is not None

    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            lease_expires_at=func.now()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    assert repo.mark_completed(
        job.task_id,
        claimed.attempt_count,
    ) is False

    db_session.commit()

    updated = repo.get_by_task_id(job.task_id)
    assert updated.status == "processing"


def test_expired_job_with_no_attempts_left_fails(
    db_session,
    sample_document,
):
    """租约过期且重试次数耗尽后，任务最终失败。"""

    from sqlalchemy import func, text, update
    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(
        sample_document.id,
        max_attempts=1,
    )
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()
    assert claimed is not None

    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            lease_expires_at=func.now()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    assert repo.fail_expired_job(job.task_id) is True
    db_session.commit()

    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "failed"
    assert updated.error_type == "LeaseExpired"
    assert updated.lease_expires_at is None

    # 已经失败的任务不能再次恢复。
    assert repo.recover_expired_job(job.task_id) is False

def test_recovery_scan_finds_pending_job(db_session, sample_document):
    """待处理任务应出现在恢复扫描结果中。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    candidates = repo.list_recovery_candidates()

    assert job.task_id in {item.task_id for item in candidates}


def test_recovery_scan_excludes_completed_job(db_session, sample_document):
    """已完成任务不应再次派发。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    assert repo.mark_completed(job.task_id, claimed.attempt_count)
    db_session.commit()

    candidates = repo.list_recovery_candidates()

    assert job.task_id not in {item.task_id for item in candidates}


def test_recovery_scan_finds_expired_job(db_session, sample_document):
    """租约过期的 processing 任务应被扫描到。"""

    from sqlalchemy import update, func, text
    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            lease_expires_at=func.now() - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    candidates = repo.list_recovery_candidates()

    assert job.task_id in {item.task_id for item in candidates}



def test_reserve_dispatch_succeeds_once(
    db_session,
    sample_document,
):
    """同一任务只能在当前预留窗口内成功派发一次。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is True
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is False
    db_session.commit()


def test_reserve_dispatch_respects_future_schedule(
    db_session,
    sample_document,
):
    """未到计划时间的任务不能提前派发。"""

    from sqlalchemy import func, text, update
    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    db_session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.task_id == job.task_id
        )
        .values(
            next_dispatch_at=func.now()
            + text("INTERVAL '5 minutes'")
        )
    )
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is False


def test_reserve_dispatch_after_window_expires(
    db_session,
    sample_document,
):
    """预留窗口过期后，可以再次获得派发资格。"""

    from sqlalchemy import func, text, update
    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is True
    db_session.commit()

    # 模拟等待窗口已经过期。
    db_session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.task_id == job.task_id
        )
        .values(
            next_dispatch_at=func.now()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is True


def test_completed_job_cannot_reserve_dispatch(
    db_session,
    sample_document,
):
    """已完成任务不能再次获得派发资格。"""

    repo = ProcessingJobRepository(db_session)
    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    assert repo.mark_completed(
        job.task_id,
        claimed.attempt_count,
    )
    db_session.commit()

    assert repo.reserve_dispatch(job.task_id) is False


def test_recover_expired_job_clears_dispatch_schedule(
    db_session,
    sample_document,
):
    """租约过期任务恢复后应允许立即重新派发。"""

    from sqlalchemy import func, text, update

    from app.models.processing_job import ProcessingJob

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None

    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == job.task_id)
        .values(
            lease_expires_at=func.clock_timestamp()
            - text("INTERVAL '1 minute'"),
            next_dispatch_at=func.clock_timestamp()
            + text("INTERVAL '5 minutes'"),
        )
    )
    db_session.commit()

    assert repo.recover_expired_job(job.task_id)
    db_session.commit()

    db_session.expire_all()
    updated = repo.get_by_task_id(job.task_id)

    assert updated.status == "pending"
    assert updated.next_dispatch_at is None
    assert updated.lease_expires_at is None

    assert repo.reserve_dispatch(job.task_id)


def test_create_retry_job_from_failed(
    db_session,
    sample_document,
):
    """失败任务允许创建新的处理任务。"""

    repo = ProcessingJobRepository(db_session)

    original = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(original.task_id)
    db_session.commit()

    assert claimed is not None

    assert repo.mark_failed(
        original.task_id,
        claimed.attempt_count,
        "ProcessingError",
        "Test failure",
    )
    db_session.commit()

    retry = repo.create_retry_job(original.task_id)
    db_session.commit()

    assert retry.task_id != original.task_id
    assert retry.document_id == original.document_id
    assert retry.status == "pending"
    assert retry.attempt_count == 0

    db_session.expire_all()
    assert repo.get_by_task_id(original.task_id).status == "failed"


def test_create_retry_job_rejects_pending(
    db_session,
    sample_document,
):
    """不能为尚未完成的任务创建手动重试。"""

    repo = ProcessingJobRepository(db_session)

    job = repo.create_job(sample_document.id)
    db_session.commit()

    assert repo.create_retry_job(job.task_id) is None


def test_create_retry_job_rejects_missing_task(
    db_session,
):
    """不存在的任务不能创建重试任务。"""

    repo = ProcessingJobRepository(db_session)

    assert repo.create_retry_job("missing-task") is None


def test_retry_job_preserves_document(
    db_session,
    sample_document,
):
    """重试任务创建后，原文档仍然存在。"""

    repo = ProcessingJobRepository(db_session)

    original = repo.create_job(sample_document.id)
    db_session.commit()

    claimed = repo.claim_job(original.task_id)
    db_session.commit()

    assert claimed is not None

    assert repo.mark_failed(
        original.task_id,
        claimed.attempt_count,
        "ProcessingError",
        "Test failure",
    )
    db_session.commit()

    retry = repo.create_retry_job(original.task_id)
    db_session.commit()

    assert retry is not None
    assert retry.document_id == sample_document.id
    assert db_session.get(Document, sample_document.id) is not None