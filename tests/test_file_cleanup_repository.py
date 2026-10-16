"""验证文件清理任务的创建、查询及状态转换。"""

from uuid import uuid4

from app.services.file_cleanup_repository import FileCleanupRepository


def test_create_cleanup_job(db_session):
    """创建清理任务后应处于 pending 状态。"""

    repo = FileCleanupRepository(db_session)
    file_id = str(uuid4())

    job = repo.create(file_id)

    assert job.file_id == file_id
    assert job.status == "pending"
    assert job.attempt_count == 0


def test_list_pending_cleanup_jobs(db_session):
    """只返回等待处理的文件清理任务。"""

    repo = FileCleanupRepository(db_session)

    first = repo.create(str(uuid4()))
    second = repo.create(str(uuid4()))

    assert repo.mark_completed(first.id)
    db_session.commit()

    pending = repo.list_pending()

    assert second.id in {job.id for job in pending}
    assert first.id not in {job.id for job in pending}


def test_mark_cleanup_completed(db_session):
    """完成清理后应记录结束时间。"""

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))

    assert repo.mark_completed(job.id)
    db_session.commit()

    db_session.expire_all()
    updated = repo.get_by_file_id(job.file_id)

    assert updated.status == "completed"
    assert updated.finished_at is not None
    assert repo.mark_completed(updated.id) is False


def test_record_cleanup_attempt(db_session):
    """每次清理尝试应递增执行次数。"""

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))

    assert repo.record_attempt(job.id)
    assert repo.record_attempt(job.id)
    db_session.commit()

    db_session.expire_all()
    updated = repo.get_by_file_id(job.file_id)

    assert updated.attempt_count == 2


def test_claim_cleanup_job_once(db_session):
    """同一清理任务只能在当前执行期间领取一次。"""

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))
    db_session.commit()

    attempt = repo.claim_cleanup_job(job.id)
    db_session.commit()

    assert attempt == 1
    assert repo.claim_cleanup_job(job.id) is None


def test_complete_claimed_cleanup_job(db_session):
    """有效执行尝试可以完成清理任务。"""

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))
    db_session.commit()

    attempt = repo.claim_cleanup_job(job.id)
    db_session.commit()

    assert attempt == 1
    assert repo.complete_claimed_job(job.id, attempt)
    db_session.commit()

    db_session.expire_all()
    updated = repo.get_by_file_id(job.file_id)

    assert updated.status == "completed"
    assert updated.lease_expires_at is None


def test_release_claimed_cleanup_job(db_session):
    """清理失败时任务可以重新进入 pending。"""

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))
    db_session.commit()

    attempt = repo.claim_cleanup_job(job.id)
    db_session.commit()

    assert repo.release_claimed_job(job.id, attempt)
    db_session.commit()

    next_attempt = repo.claim_cleanup_job(job.id)

    assert next_attempt == 2


def test_expired_cleanup_rejects_old_worker(db_session):
    """任务恢复并被重新领取后，旧执行编号不能完成任务。"""

    from sqlalchemy import func, text, update
    from app.models.file_cleanup_job import FileCleanupJob

    repo = FileCleanupRepository(db_session)
    job = repo.create(str(uuid4()))
    db_session.commit()

    first_attempt = repo.claim_cleanup_job(job.id)
    db_session.commit()

    db_session.execute(
        update(FileCleanupJob)
        .where(FileCleanupJob.id == job.id)
        .values(
            lease_expires_at=func.clock_timestamp()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    assert repo.recover_expired_cleanup_job(job.id)
    db_session.commit()

    second_attempt = repo.claim_cleanup_job(job.id)
    db_session.commit()

    assert second_attempt == first_attempt + 1

    assert not repo.complete_claimed_job(
        job.id,
        first_attempt,
    )

    assert repo.complete_claimed_job(
        job.id,
        second_attempt,
    )
