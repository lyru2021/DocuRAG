"""
执行论文 PDF 后台解析任务，并管理任务状态及失败处理。
"""

from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.services.file_storage import LocalFileStorage
from app.services.paper_processing_service import PaperProcessingService
from app.services.processing_job_repository import ProcessingJobRepository
from app.services.processing_errors import PermanentProcessingError, is_retryable_error, retry_delay
from app.worker.celery_app import celery_app
from app.worker.lease_heartbeat import LeaseHeartbeat




@celery_app.task(
    name="docurag.process_paper",
    bind=True,
    acks_late=True,
)
def process_paper_task(self, task_id: str):
    """根据任务 ID 解析 PDF，并将结果持久化。"""

    # 阶段一：短事务认领任务。
    with SessionLocal() as db:
        jobs = ProcessingJobRepository(db)
        job = jobs.claim_job(task_id)

        if job is None:
            db.rollback()
            return {"status": "skipped"}

        document_id = job.document_id
        attempt_count = job.attempt_count
        db.commit()

    try:
        # 阶段二：读取原始 PDF。
        # Celery 只接收 task_id，不在消息中传输 PDF 字节。
        with SessionLocal() as db:
            document = db.get(Document, document_id)

            if document is None:
                raise PermanentProcessingError(
                    "Document not found"
                )

            if not document.file_id or not document.content_hash:
                raise PermanentProcessingError(
                    "Original PDF metadata missing"
                )

            storage = LocalFileStorage(
                Path(get_settings().UPLOAD_DIR)
            )

            path = storage.get_pdf_path(document.file_id)

            if path is None:
                raise PermanentProcessingError(
                    "Original PDF not found"
                )

            if not storage.verify_hash(
                document.file_id,
                document.content_hash,
            ):
                raise PermanentProcessingError(
                    "Original PDF hash mismatch"
                )

            pdf_bytes = path.read_bytes()

        # 阶段三：处理期间续租，解析结果与完成状态统一提交。
        heartbeat = LeaseHeartbeat(
            task_id=task_id,
            attempt_count=attempt_count,
            session_factory=SessionLocal,
        )

        heartbeat.start()

        try:
            with SessionLocal() as db:
                processor = PaperProcessingService(db)
                jobs = ProcessingJobRepository(db)

                chunk_count = processor.process_pdf(
                    document_id=document_id,
                    pdf_bytes=pdf_bytes,
                )

                if heartbeat.lease_lost:
                    db.rollback()
                    return {"status": "stale"}

                success = jobs.mark_completed(
                    task_id=task_id,
                    attempt_count=attempt_count,
                )

                if not success:
                    db.rollback()
                    return {"status": "stale"}

                # 完成状态与解析结果在同一事务中提交。
                db.commit()

        finally:
            # 先结束主线程事务，再等待心跳退出。
            heartbeat.stop()

        return {
            "status": "completed",
            "document_id": document_id,
            "chunk_count": chunk_count,
        }

    
    except Exception as exc:
        # 根据异常类型决定重试还是最终失败。

        # 保留一个独立事务，避免提交解析过程中的半成品数据。
        with SessionLocal() as db:
            jobs = ProcessingJobRepository(db)

            job = jobs.get_by_task_id(task_id)

            # 只有当前执行尝试仍有效，才允许修改任务状态。
            if (
                job is None
                or job.status != "processing"
                or job.attempt_count != attempt_count
            ):
                db.rollback()
                raise

            # 将 ORM 字段保存为普通整数，避免关闭 Session 后再访问数据库对象。
            max_attempts = job.max_attempts

            can_retry = (
                is_retryable_error(exc)
                and attempt_count < max_attempts
            )

            if can_retry:
                updated = jobs.prepare_retry(
                task_id=task_id,
                attempt_count=attempt_count,
                error_type=type(exc).__name__,
                error_message=str(exc),
                delay_seconds=retry_delay(attempt_count),
            )
            else:
                updated = jobs.mark_failed(
                    task_id=task_id,
                    attempt_count=attempt_count,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )

            if not updated:
                db.rollback()
                raise

            db.commit()

        if can_retry:
            # 已将下一次派发时间保存到 PostgreSQL。
            # 不再调用 Celery.retry，避免两套重试调度互相竞争。
            return {
                "status": "retry_scheduled",
                "task_id": task_id,
                "attempt_count": attempt_count,
            }

        raise

