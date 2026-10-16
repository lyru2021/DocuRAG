"""验证文档删除、活跃任务保护及文件清理。"""
import pytest
from unittest.mock import patch

from app.services.document_deletion_service import DocumentDeletionService
from app.services.processing_job_repository import ProcessingJobRepository


def test_delete_missing_document(db_session):
    """不存在的文档应返回 not_found。"""

    service = DocumentDeletionService(db_session)

    assert service.delete(-1) == "not_found"


def test_delete_rejects_active_job(
    db_session,
    sample_document,
):
    """文档存在活跃任务时禁止删除。"""

    jobs = ProcessingJobRepository(db_session)
    jobs.create_job(sample_document.id)
    db_session.commit()

    service = DocumentDeletionService(db_session)

    assert service.delete(sample_document.id) == "active_job"
    assert service.documents.get(sample_document.id) is not None


def test_delete_document_creates_cleanup_job(
    db_session,
    sample_document,
):
    """删除文档时应持久化原始 PDF 清理任务。"""

    from uuid import uuid4

    from app.services.file_cleanup_repository import (
        FileCleanupRepository,
    )

    file_id = str(uuid4())
    document_id = sample_document.id

    sample_document.file_id = file_id
    db_session.commit()

    service = DocumentDeletionService(db_session)

    result = service.delete(document_id)

    assert result == "deleted"
    assert service.documents.get(document_id) is None

    cleanup = FileCleanupRepository(db_session).get_by_file_id(
        file_id
    )

    assert cleanup is not None
    assert cleanup.status == "pending"
    assert cleanup.attempt_count == 0

def test_cleanup_registration_failure_preserves_document(
    db_session,
    sample_document,
):
    """清理任务登记失败时，文档删除事务必须回滚。"""

    from unittest.mock import patch
    from uuid import uuid4

    from app.services.file_cleanup_repository import (
        FileCleanupRepository,
    )

    sample_document.file_id = str(uuid4())
    document_id = sample_document.id
    db_session.commit()

    service = DocumentDeletionService(db_session)

    with patch.object(
        FileCleanupRepository,
        "create",
        side_effect=RuntimeError("Cleanup registration failed"),
    ):
        with pytest.raises(
            RuntimeError,
            match="Cleanup registration failed",
        ):
            service.delete(document_id)

    db_session.expire_all()

    assert service.documents.get(document_id) is not None


def test_delete_rejects_active_retry_job(
    db_session,
    sample_document,
):
    """创建新重试任务后，不允许删除该文档。"""

    from app.services.processing_job_repository import (
        ProcessingJobRepository,
    )

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

    retry = jobs.create_retry_job(original.task_id)
    db_session.commit()

    assert retry is not None

    service = DocumentDeletionService(db_session)

    assert service.delete(sample_document.id) == "active_job"
    assert service.documents.get(sample_document.id) is not None