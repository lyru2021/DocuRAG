"""验证文件清理成功、失败保留及重复执行行为。"""

from unittest.mock import Mock
from uuid import uuid4

from app.services.file_cleanup_repository import FileCleanupRepository
from app.services.file_cleanup_service import FileCleanupService


def test_cleanup_file_success(db_session):
    """文件删除成功后，应将任务标记为 completed。"""

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    storage = Mock()
    service = FileCleanupService(db_session, storage)

    result = service.cleanup_once()

    assert result["completed"] == 1
    assert result["errors"] == 0

    storage.delete_pdf.assert_called_once_with(job.file_id)

    db_session.expire_all()
    updated = jobs.get_by_file_id(job.file_id)

    assert updated.status == "completed"
    assert updated.attempt_count == 1
    assert updated.finished_at is not None


def test_cleanup_failure_keeps_pending(db_session):
    """文件删除失败时，应保留任务供下次重试。"""

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    storage = Mock()
    storage.delete_pdf.side_effect = OSError("Disk unavailable")

    service = FileCleanupService(db_session, storage)
    result = service.cleanup_once()

    assert result["completed"] == 0
    assert result["errors"] == 1

    db_session.expire_all()
    updated = jobs.get_by_file_id(job.file_id)

    assert updated.status == "pending"
    assert updated.attempt_count == 1


def test_cleanup_completed_job_not_repeated(db_session):
    """已经完成的清理任务不应再次删除文件。"""

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    storage = Mock()
    service = FileCleanupService(db_session, storage)

    first = service.cleanup_once()
    second = service.cleanup_once()

    assert first["completed"] == 1
    assert second["completed"] == 0
    storage.delete_pdf.assert_called_once_with(job.file_id)


def test_cleanup_recovers_expired_job(db_session):
    """租约过期的清理任务应恢复并执行删除。"""

    from uuid import uuid4
    from unittest.mock import Mock

    from sqlalchemy import func, text, update
    from app.models.file_cleanup_job import FileCleanupJob

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    first_attempt = jobs.claim_cleanup_job(job.id)
    db_session.commit()

    assert first_attempt == 1

    db_session.execute(
        update(FileCleanupJob)
        .where(FileCleanupJob.id == job.id)
        .values(
            lease_expires_at=func.clock_timestamp()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    storage = Mock()
    service = FileCleanupService(db_session, storage)

    result = service.cleanup_once()

    assert result["recovered"] == 1
    assert result["completed"] == 1

    db_session.expire_all()
    updated = jobs.get_by_file_id(job.file_id)

    assert updated.status == "completed"
    assert updated.attempt_count == 2
    storage.delete_pdf.assert_called_once_with(job.file_id)


def test_cleanup_claimed_job_not_repeated(db_session):
    """租约有效的 processing 任务不能再次领取。"""

    from uuid import uuid4
    from unittest.mock import Mock

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    attempt = jobs.claim_cleanup_job(job.id)
    db_session.commit()

    assert attempt == 1

    storage = Mock()
    service = FileCleanupService(db_session, storage)

    result = service.cleanup_once()

    assert result["completed"] == 0
    storage.delete_pdf.assert_not_called()


def test_cleanup_failure_can_retry(db_session):
    """清理失败释放任务后，下次扫描能够重新领取。"""

    from uuid import uuid4
    from unittest.mock import Mock

    jobs = FileCleanupRepository(db_session)
    job = jobs.create(str(uuid4()))
    db_session.commit()

    storage = Mock()
    storage.delete_pdf.side_effect = [
        OSError("Temporary disk failure"),
        None,
    ]

    service = FileCleanupService(db_session, storage)

    first = service.cleanup_once()
    second = service.cleanup_once()

    assert first["errors"] == 1
    assert second["completed"] == 1

    db_session.expire_all()
    updated = jobs.get_by_file_id(job.file_id)

    assert updated.status == "completed"
    assert updated.attempt_count == 2
    assert storage.delete_pdf.call_count == 2