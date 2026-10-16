"""安全清理指定心跳实验任务及其原始 PDF。"""

from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.services.document_repository import DocumentRepository
from app.services.file_storage import LocalFileStorage
from app.services.processing_job_repository import ProcessingJobRepository


TASK_ID = "4b462977-a469-418d-96e0-0314c0bf7324"
EXPECTED_FILENAME = "heartbeat-integration-test.pdf"


def main():
    with SessionLocal() as db:
        jobs = ProcessingJobRepository(db)
        job = jobs.get_by_task_id(TASK_ID)

        if job is None:
            print("实验任务不存在，无需清理。")
            return

        document = db.get(Document, job.document_id)

        if document is None:
            raise RuntimeError("任务对应的 Document 不存在")

        if document.filename != EXPECTED_FILENAME:
            raise RuntimeError(
                f"文件名不匹配，拒绝删除：{document.filename}"
            )

        if job.status != "processing":
            raise RuntimeError(
                f"任务状态不是 processing，拒绝删除：{job.status}"
            )

        document_id = document.id
        file_id = document.file_id

        if not file_id:
            raise RuntimeError("缺少 file_id，拒绝删除")

        # 优先删除数据库记录，成功后再清理原始文件。
        repository = DocumentRepository(db)

        if not repository.delete(document_id):
            raise RuntimeError("数据库文档删除失败")

        storage = LocalFileStorage(
            Path(get_settings().UPLOAD_DIR)
        )
        storage.delete_pdf(file_id)

        print(f"已删除实验任务：{TASK_ID}")
        print(f"已删除文档：{document_id}")
        print(f"已清理原始 PDF：{file_id}")


if __name__ == "__main__":
    main()