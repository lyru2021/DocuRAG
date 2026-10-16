"""使用真实 PostgreSQL 连接验证任务租约心跳续期。"""

from datetime import timedelta

from sqlalchemy import select, func

from app.db.session import SessionLocal
from app.services.async_upload_service import AsyncUploadService
from app.services.processing_job_repository import ProcessingJobRepository
from app.worker.lease_heartbeat import LeaseHeartbeat

import fitz


def main():
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Heartbeat integration test")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    with SessionLocal() as db:
        service = AsyncUploadService(db)
        document, task_id = service.create_paper_job(
            filename="heartbeat-integration-test.pdf",
            pdf_bytes=pdf_bytes,
        )

        jobs = ProcessingJobRepository(db)
        claimed = jobs.claim_job(task_id)

        assert claimed is not None

        attempt_count = claimed.attempt_count
        before_lease = claimed.lease_expires_at
        db.commit()

    heartbeat = LeaseHeartbeat(
        task_id=task_id,
        attempt_count=attempt_count,
        interval_seconds=0.2,
        session_factory=SessionLocal,
    )

    heartbeat.start()

    try:
        if not heartbeat._renewed_event.wait(timeout=5):
            raise RuntimeError("Heartbeat did not renew in time")

    finally:
        heartbeat.stop()

    with SessionLocal() as db:
        jobs = ProcessingJobRepository(db)
        updated = jobs.get_by_task_id(task_id)

        assert not heartbeat.lease_lost
        assert not heartbeat._thread.is_alive()
        assert updated.status == "processing"
        assert updated.lease_expires_at > before_lease

        print(f"task_id={task_id}")
        print(f"before_lease={before_lease}")
        print(f"after_lease={updated.lease_expires_at}")
        print("heartbeat_renewal=SUCCESS")


if __name__ == "__main__":
    main()