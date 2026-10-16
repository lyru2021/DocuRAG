"""验证租约失效时，论文解析结果与任务状态一起回滚。"""

from sqlalchemy import func, text, update

from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.services.paper_processing_service import PaperProcessingService
from app.services.processing_job_repository import ProcessingJobRepository


def test_expired_worker_cannot_commit_parsed_pdf(
    db_session,
    sample_document,
):
    """租约过期后不得提交旧 Worker 的解析结果。"""

    import fitz

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Stale worker test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    jobs = ProcessingJobRepository(db_session)
    job = jobs.create_job(sample_document.id)
    task_id = job.task_id
    document_id = sample_document.id
    db_session.commit()

    claimed = jobs.claim_job(task_id)
    assert claimed is not None
    attempt_count = claimed.attempt_count
    db_session.commit()

    # 模拟旧 Worker 的租约已经过期。
    db_session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.task_id == task_id)
        .values(
            lease_expires_at=func.clock_timestamp()
            - text("INTERVAL '1 minute'")
        )
    )
    db_session.commit()

    processor = PaperProcessingService(db_session)

    processor.process_pdf(
        document_id=document_id,
        pdf_bytes=pdf_bytes,
    )

    # 解析虽然成功，但任务完成条件必须失败。
    completed = jobs.mark_completed(
        task_id=task_id,
        attempt_count=attempt_count,
    )

    assert completed is False
    db_session.rollback()

    # 回滚后重新读取，确认解析结果未持久化。
    db_session.expire_all()
    document = db_session.get(Document, document_id)

    assert document.parse_status != "parsed"
    assert document.extracted_text is None

    updated = jobs.get_by_task_id(task_id)
    assert updated.status == "processing"