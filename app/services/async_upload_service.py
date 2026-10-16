"""
保存待处理的原始 PDF，并在同一事务中创建文档与处理任务。
"""
import logging
import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.services.file_storage import LocalFileStorage
from app.services.processing_job_repository import (
    ProcessingJobRepository,
)

logger = logging.getLogger(__name__)
class AsyncUploadService:
    """负责保存原文件并创建 pending 任务，不执行 PDF 文本解析。"""

    def __init__(self, db: Session):
        self.db = db
        self.storage = LocalFileStorage(
            Path(get_settings().UPLOAD_DIR)
        )

    def create_paper_job(
        self,
        filename: str,
        pdf_bytes: bytes,
    ) -> tuple[Document, str]:
        """
        创建待处理论文及任务。

        返回：
            (Document, task_id)

        注意：
            文件系统不能参与 PostgreSQL 事务，
            因此需要在数据库失败时清理已保存的文件。
        """

        if not pdf_bytes:
            raise ValueError("Empty PDF file")

        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")

        file_id = str(uuid4())
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # 先保存原文件，Worker 之后通过 file_id 读取。
        self.storage.save_pdf(file_id, pdf_bytes)

        try:
            document = Document(
                title=filename,
                filename=filename,
                file_id=file_id,
                media_type="application/pdf",
                file_size=len(pdf_bytes),
                content_hash=content_hash,
                parse_status="pending",
                text_length=0,
                extracted_text=None,
            )

            self.db.add(document)
            self.db.flush()

            jobs = ProcessingJobRepository(self.db)
            job = jobs.create_job(document_id=document.id)

            # Document 与 ProcessingJob 一起提交。
            self.db.commit()

            return document, job.task_id

        except Exception:
            self.db.rollback()

            try:
                self.storage.delete_pdf(file_id)
            except Exception:
                logger.exception(
                    "Failed to remove uploaded PDF after database error: file_id=%s",
                    file_id,
                )

            raise
