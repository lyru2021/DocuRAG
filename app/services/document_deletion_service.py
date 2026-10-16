"""协调文档数据库删除、活跃任务检查与本地 PDF 清理。"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.processing_job import ProcessingJob
from app.models.document import Document
from app.services.document_repository import DocumentRepository
from app.services.file_storage import LocalFileStorage
from app.services.file_cleanup_repository import FileCleanupRepository


class DocumentDeletionService:
    """协调文档记录与原始 PDF 的删除。"""

    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.storage = LocalFileStorage(
            Path(get_settings().UPLOAD_DIR)
        )

    def delete(self, document_id: int) -> str:
        """锁定文档后检查活跃任务，原子登记清理并删除文档。"""

        try:
            document = self.db.scalar(
                select(Document)
                .where(Document.id == document_id)
                .with_for_update()
            )

            if document is None:
                self.db.rollback()
                return "not_found"

            active_job = self.db.scalar(
                select(ProcessingJob.id)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.status.in_(["pending", "processing"]),
                )
                .limit(1)
            )

            if active_job is not None:
                self.db.rollback()
                return "active_job"

            if document.file_id:
                FileCleanupRepository(self.db).create(
                    document.file_id
                )

            self.db.delete(document)
            self.db.commit()

            return "deleted"

        except Exception:
            self.db.rollback()
            raise