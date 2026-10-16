"""
验证 Celery 论文处理任务的真实异常分支及状态变化。
"""
import fitz
import pytest

from unittest.mock import patch
from datetime import timedelta, timezone, datetime
from sqlalchemy import func, select


from app.core.config import get_settings
from app.models.document import Document
from app.services.file_storage import LocalFileStorage
from app.services.processing_errors import TransientProcessingError
from app.services.processing_job_repository import ProcessingJobRepository
from app.worker.paper_tasks import process_paper_task



def test_worker_retries_transient_failure(
    db_session,
    sample_document,
    tmp_path,
    monkeypatch,
):
    """临时解析失败后，任务应恢复 pending 并安排数据库定时重试。"""

    import hashlib
    from datetime import timedelta
    from unittest.mock import patch
    from uuid import uuid4

    import fitz
    from sqlalchemy import func, select

    import app.worker.paper_tasks as worker_module

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: db_session,
    )
    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Retry test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    file_id = str(uuid4())
    LocalFileStorage(tmp_path).save_pdf(file_id, pdf_bytes)

    sample_document.file_id = file_id
    sample_document.media_type = "application/pdf"
    sample_document.content_hash = hashlib.sha256(
        pdf_bytes
    ).hexdigest()

    jobs = ProcessingJobRepository(db_session)
    job = jobs.create_job(sample_document.id)
    task_id = job.task_id
    db_session.commit()

    before_run = db_session.scalar(
        select(func.clock_timestamp())
    )

    with (
        patch.object(
            worker_module.PaperProcessingService,
            "process_pdf",
            side_effect=TransientProcessingError(
                "Temporary parser failure"
            ),
        ),
        patch.object(
            process_paper_task,
            "retry",
        ) as retry_mock,
    ):
        result = process_paper_task(task_id)

    after_run = db_session.scalar(
        select(func.clock_timestamp())
    )

    assert result["status"] == "retry_scheduled"
    assert result["task_id"] == task_id
    assert result["attempt_count"] == 1
    retry_mock.assert_not_called()

    db_session.expire_all()
    updated = jobs.get_by_task_id(task_id)

    assert updated.status == "pending"
    assert updated.attempt_count == 1
    assert updated.error_type == "TransientProcessingError"
    assert updated.next_dispatch_at is not None

    # 首次失败应安排约 2 秒后重新派发。
    assert (
        updated.next_dispatch_at
        >= before_run + timedelta(seconds=2)
    )
    assert (
        updated.next_dispatch_at
        <= after_run + timedelta(seconds=2)
    )



def test_worker_does_not_retry_permanent_failure(
    db_session,
    sample_document,
    tmp_path,
    monkeypatch,
):
    """原文件缺失属于永久错误，任务应直接失败而不是重试。"""

    import app.worker.paper_tasks as worker_module

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: db_session,
    )

    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    # 使用有效 UUID，但故意不创建对应的 PDF 文件。
    from uuid import uuid4

    sample_document.file_id = str(uuid4())
    sample_document.content_hash = "a" * 64
    sample_document.media_type = "application/pdf"
    db_session.flush()

    jobs = ProcessingJobRepository(db_session)
    job = jobs.create_job(sample_document.id)
    task_id = job.task_id
    db_session.commit()

    with patch.object(process_paper_task, "retry") as retry_mock:
        with pytest.raises(
            worker_module.PermanentProcessingError,
            match="Original PDF not found",
        ):
            process_paper_task(task_id)

    db_session.expire_all()
    updated = jobs.get_by_task_id(task_id)

    assert updated.status == "failed"
    assert updated.attempt_count == 1
    assert updated.error_type == "PermanentProcessingError"

    # 永久错误绝不安排自动重试。
    retry_mock.assert_not_called()


def test_worker_stops_retrying_after_max_attempts(
    db_session,
    sample_document,
    tmp_path,
    monkeypatch,
):
    """达到最大执行次数时，即使是临时错误也必须最终失败。"""

    import hashlib
    from uuid import uuid4

    import app.worker.paper_tasks as worker_module

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: db_session,
    )

    monkeypatch.setattr(
        get_settings(),
        "UPLOAD_DIR",
        str(tmp_path),
    )

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Retry limit test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    file_id = str(uuid4())
    LocalFileStorage(tmp_path).save_pdf(file_id, pdf_bytes)

    sample_document.file_id = file_id
    sample_document.content_hash = hashlib.sha256(
        pdf_bytes
    ).hexdigest()
    sample_document.media_type = "application/pdf"
    db_session.flush()

    jobs = ProcessingJobRepository(db_session)

    # 最多一次执行，用于模拟重试额度已经耗尽。
    job = jobs.create_job(
        sample_document.id,
        max_attempts=1,
    )
    task_id = job.task_id
    db_session.commit()



    # 模拟解析阶段发生临时错误，验证新的数据库驱动重试策略。
    with (
        patch.object(
            worker_module.PaperProcessingService,
            "process_pdf",
            side_effect=TransientProcessingError(
                "Temporary parser failure"
            ),
        ),
        patch.object(
            process_paper_task,
            "retry",
        ) as retry_mock,
    ):
        with pytest.raises(
            TransientProcessingError,
            match="Temporary parser failure",
        ):
            process_paper_task(task_id)

    retry_mock.assert_not_called()

    # 读取 Worker 执行后的数据库状态。
    db_session.expire_all()
    updated = jobs.get_by_task_id(task_id)

    assert updated.status == "failed"
    assert updated.attempt_count == 1
    assert updated.error_type == "TransientProcessingError"
    assert updated.finished_at is not None
    assert updated.lease_expires_at is None
    assert updated.next_dispatch_at is None


def test_worker_starts_and_stops_heartbeat(
    db_session,
    sample_document,
    tmp_path,
    monkeypatch,
):
    """Worker 正常处理论文时应启动并停止心跳。"""

def test_worker_rolls_back_when_heartbeat_lost(
    db_session,
    sample_document,
    tmp_path,
    monkeypatch,
):
    """失去租约时不得提交 PDF 解析结果。"""