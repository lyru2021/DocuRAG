"""执行本地 PDF 清理任务，并持久化执行结果。"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.file_cleanup_repository import FileCleanupRepository
from app.services.file_storage import LocalFileStorage


logger = logging.getLogger(__name__)


class FileCleanupService:
    """协调数据库清理记录与本地文件删除。"""

    def __init__(self, db: Session, storage=None):
        self.db = db
        self.jobs = FileCleanupRepository(db)
        self.storage = storage or LocalFileStorage(
            Path(get_settings().UPLOAD_DIR)
        )

    def cleanup_once(self, limit: int = 100) -> dict:
        """原子领取文件清理任务，执行删除并恢复过期租约。"""

        candidates = self.jobs.list_recovery_candidates(
            limit=limit
        )

        completed = 0
        recovered = 0
        errors = 0

        for candidate in candidates:
            job_id = candidate.id
            file_id = candidate.file_id

            try:
                if candidate.status == "processing":
                    changed = self.jobs.recover_expired_cleanup_job(
                        job_id
                    )

                    if not changed:
                        self.db.rollback()
                        continue

                    self.db.commit()
                    recovered += 1

                # 只有一个 Worker 能成功领取当前 pending 任务。
                attempt = self.jobs.claim_cleanup_job(job_id)

                if attempt is None:
                    self.db.rollback()
                    continue

                # 必须先提交领取事务，再执行文件删除。
                self.db.commit()

                try:
                    self.storage.delete_pdf(file_id)

                except Exception:
                    self.db.rollback()

                    # 仅当前执行尝试可以释放任务。
                    released = self.jobs.release_claimed_job(
                        job_id,
                        attempt,
                    )

                    if released:
                        self.db.commit()
                    else:
                        self.db.rollback()

                    errors += 1
                    logger.exception(
                        "File cleanup failed: job_id=%s file_id=%s",
                        job_id,
                        file_id,
                    )
                    continue

                # 删除成功后仍需验证当前执行版本和租约。
                if self.jobs.complete_claimed_job(job_id, attempt):
                    self.db.commit()
                    completed += 1
                else:
                    self.db.rollback()

                    logger.warning(
                        "File cleanup lease lost: job_id=%s attempt=%s",
                        job_id,
                        attempt,
                    )

            except Exception:
                self.db.rollback()
                errors += 1

                logger.exception(
                    "File cleanup transaction failed: job_id=%s",
                    job_id,
                )

        return {
            "scanned": len(candidates),
            "recovered": recovered,
            "completed": completed,
            "errors": errors,
        }