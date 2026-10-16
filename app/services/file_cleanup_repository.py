"""管理本地文件清理任务的创建、查询和状态更新。"""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text, update

from app.models.file_cleanup_job import FileCleanupJob


class FileCleanupRepository:
    """管理文件清理任务的数据库操作。"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, file_id: str) -> FileCleanupJob:
        """创建待清理任务，不在 Repository 内提交事务。"""

        job = FileCleanupJob(
            file_id=file_id,
            status="pending",
        )
        self.db.add(job)
        self.db.flush()
        return job

    def get_by_file_id(self, file_id: str) -> FileCleanupJob | None:
        """根据文件 ID 查询清理任务。"""

        return self.db.scalar(
            select(FileCleanupJob).where(
                FileCleanupJob.file_id == file_id
            )
        )

    def list_pending(self, limit: int = 100) -> list[FileCleanupJob]:
        """查询等待清理的文件。"""

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        statement = (
            select(FileCleanupJob)
            .where(FileCleanupJob.status == "pending")
            .order_by(FileCleanupJob.id)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    def mark_completed(self, job_id: int) -> bool:
        """将文件清理任务标记为已完成。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "pending",
            )
            .values(
                status="completed",
                finished_at=func.clock_timestamp(),
            )
            .returning(FileCleanupJob.id)
        )

        return self.db.scalar(statement) is not None

    def record_attempt(self, job_id: int) -> bool:
        """记录一次文件清理尝试。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "pending",
            )
            .values(
                attempt_count=FileCleanupJob.attempt_count + 1,
            )
            .returning(FileCleanupJob.id)
        )

        return self.db.scalar(statement) is not None
    
    def claim_cleanup_job(self, job_id: int) -> int | None:
        """原子领取待清理任务，返回当前执行编号。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "pending",
            )
            .values(
                status="processing",
                attempt_count=FileCleanupJob.attempt_count + 1,
                started_at=func.clock_timestamp(),
                lease_expires_at=func.clock_timestamp()
                + text("INTERVAL '5 minutes'"),
                finished_at=None,
            )
            .returning(FileCleanupJob.attempt_count)
        )

        return self.db.scalar(statement)
    
    def complete_claimed_job(
        self,
        job_id: int,
        attempt_count: int,
    ) -> bool:
        """仅允许持有有效租约的执行尝试完成清理。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "processing",
                FileCleanupJob.attempt_count == attempt_count,
                FileCleanupJob.lease_expires_at
                > func.clock_timestamp(),
            )
            .values(
                status="completed",
                lease_expires_at=None,
                finished_at=func.clock_timestamp(),
            )
            .returning(FileCleanupJob.id)
        )

        return self.db.scalar(statement) is not None


    def release_claimed_job(
        self,
        job_id: int,
        attempt_count: int,
    ) -> bool:
        """清理失败后释放当前执行尝试。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "processing",
                FileCleanupJob.attempt_count == attempt_count,
                FileCleanupJob.lease_expires_at
                > func.clock_timestamp(),
            )
            .values(
                status="pending",
                started_at=None,
                lease_expires_at=None,
            )
            .returning(FileCleanupJob.id)
        )

        return self.db.scalar(statement) is not None


    def recover_expired_cleanup_job(self, job_id: int) -> bool:
        """将租约过期的清理任务恢复为待处理状态。"""

        statement = (
            update(FileCleanupJob)
            .where(
                FileCleanupJob.id == job_id,
                FileCleanupJob.status == "processing",
                FileCleanupJob.lease_expires_at
                < func.clock_timestamp(),
            )
            .values(
                status="pending",
                started_at=None,
                lease_expires_at=None,
            )
            .returning(FileCleanupJob.id)
        )

        return self.db.scalar(statement) is not None
    


    def list_recovery_candidates(
        self,
        limit: int = 100,
    ) -> list[FileCleanupJob]:
        """查询待领取及租约过期的文件清理任务。"""

        from sqlalchemy import or_, and_

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        statement = (
            select(FileCleanupJob)
            .where(
                or_(
                    FileCleanupJob.status == "pending",
                    and_(
                        FileCleanupJob.status == "processing",
                        FileCleanupJob.lease_expires_at
                        < func.clock_timestamp(),
                    ),
                )
            )
            .order_by(FileCleanupJob.id)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())