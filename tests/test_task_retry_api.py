"""验证手动重试 API 的任务创建、状态冲突及消息派发。"""

from unittest.mock import patch

from app.models.processing_job import ProcessingJob
from app.services.processing_job_repository import ProcessingJobRepository


def test_retry_failed_task_creates_new_job(
    client,
    db_session,
    sample_document,
):
    """失败任务应创建新的任务记录，并保留历史。"""

    jobs = ProcessingJobRepository(db_session)
    original = jobs.create_job(sample_document.id)
    db_session.commit()

    claimed = jobs.claim_job(original.task_id)
    db_session.commit()

    assert claimed is not None

    assert jobs.mark_failed(
        original.task_id,
        claimed.attempt_count,
        "ProcessingError",
        "Test failure",
    )
    db_session.commit()

    with patch(
        "app.api.tasks.process_paper_task.apply_async"
    ) as dispatch:
        response = client.post(
            f"/tasks/{original.task_id}/retry"
        )

    assert response.status_code == 202

    body = response.json()
    assert body["task_id"] != original.task_id
    assert body["document_id"] == sample_document.id
    assert body["dispatch_status"] == "sent"

    dispatch.assert_called_once_with(
        args=[body["task_id"]],
        task_id=body["task_id"],
    )

    db_session.expire_all()

    assert jobs.get_by_task_id(original.task_id).status == "failed"
    assert jobs.get_by_task_id(body["task_id"]).status == "pending"


def test_retry_pending_task_returns_409(
    client,
    db_session,
    sample_document,
):
    """不能手动重试尚未结束的任务。"""

    jobs = ProcessingJobRepository(db_session)
    job = jobs.create_job(sample_document.id)
    db_session.commit()

    response = client.post(f"/tasks/{job.task_id}/retry")

    assert response.status_code == 409


def test_retry_missing_task_returns_404(client):
    """不存在的任务应返回 404。"""

    response = client.post("/tasks/missing-task/retry")

    assert response.status_code == 404


def test_retry_dispatch_failure_keeps_pending(
    client,
    db_session,
    sample_document,
):
    """Redis 派发失败后，新任务保留 pending。"""

    jobs = ProcessingJobRepository(db_session)
    original = jobs.create_job(sample_document.id)
    db_session.commit()

    claimed = jobs.claim_job(original.task_id)
    db_session.commit()

    assert claimed is not None

    assert jobs.mark_failed(
        original.task_id,
        claimed.attempt_count,
        "ProcessingError",
        "Test failure",
    )
    db_session.commit()

    with patch(
        "app.api.tasks.process_paper_task.apply_async",
        side_effect=ConnectionError("Redis unavailable"),
    ):
        response = client.post(
            f"/tasks/{original.task_id}/retry"
        )

    assert response.status_code == 202

    body = response.json()
    assert body["dispatch_status"] == "deferred"

    db_session.expire_all()
    updated = jobs.get_by_task_id(body["task_id"])

    assert updated.status == "pending"
    assert updated.next_dispatch_at is not None


def test_retry_same_failed_task_twice_returns_409(
    client,
    db_session,
    sample_document,
):
    """同一失败任务连续重试时，只能创建一个活跃任务。"""

    jobs = ProcessingJobRepository(db_session)
    original = jobs.create_job(sample_document.id)
    db_session.commit()

    claimed = jobs.claim_job(original.task_id)
    db_session.commit()

    assert claimed is not None

    assert jobs.mark_failed(
        original.task_id,
        claimed.attempt_count,
        "ProcessingError",
        "Test failure",
    )
    db_session.commit()

    with patch("app.api.tasks.process_paper_task.apply_async"):
        first = client.post(f"/tasks/{original.task_id}/retry")
        second = client.post(f"/tasks/{original.task_id}/retry")

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"] == (
        "Document already has an active task"
    )

    db_session.expire_all()

    active_jobs = [
        job
        for job in db_session.query(ProcessingJob).filter(
            ProcessingJob.document_id == sample_document.id,
            ProcessingJob.status.in_(["pending", "processing"]),
        ).all()
    ]

    assert len(active_jobs) == 1
    assert active_jobs[0].task_id == first.json()["task_id"]


def test_retry_completed_task_returns_409(
    client,
    db_session,
    sample_document,
):
    """已经完成的任务不能手动重试。"""

    jobs = ProcessingJobRepository(db_session)
    job = jobs.create_job(sample_document.id)
    db_session.commit()

    claimed = jobs.claim_job(job.task_id)
    db_session.commit()

    assert claimed is not None
    assert jobs.mark_completed(
        job.task_id,
        claimed.attempt_count,
    )
    db_session.commit()

    response = client.post(f"/tasks/{job.task_id}/retry")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only failed tasks can be retried"
    )