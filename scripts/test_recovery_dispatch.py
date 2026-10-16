"""创建未发送 Celery 消息的 PDF 任务，验证自动恢复派发。"""

import fitz

from app.db.session import SessionLocal
from app.services.async_upload_service import AsyncUploadService
from app.services.processing_job_repository import ProcessingJobRepository


def main():
    pdf = fitz.open()
    pdf.new_page().insert_text(
        (72, 72),
        "DocuRAG automatic recovery integration test",
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()

    with SessionLocal() as db:
        service = AsyncUploadService(db=db)

        document, task_id = service.create_paper_job(
            filename="recovery-test.pdf",
            pdf_bytes=pdf_bytes,
        )

        document_id = document.id

        jobs = ProcessingJobRepository(db)
        job = jobs.get_by_task_id(task_id)

        print(f"document_id={document_id}")
        print(f"task_id={task_id}")
        print(f"status={job.status}")
        print("No initial Celery message was sent.")


if __name__ == "__main__":
    main()
