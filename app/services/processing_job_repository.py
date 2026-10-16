"""
管理论文异步处理任务的创建、状态查询和状态更新。
"""
from uuid import uuid4
from datetime import timedelta

from sqlalchemy import func, select, update, text, and_, or_
from sqlalchemy.orm import Session

from app.models.processing_job import ProcessingJob
from app.models.document import Document


class ProcessingJobRepository:
    """
    异步论文处理任务的数据访问层。

    职责：
    - 创建待处理任务
    - 查询任务状态
    - 原子认领任务
    - 标记处理完成
    - 记录处理失败

    约定：
    本 Repository 的写操作由调用方负责 commit。
    这样后续 Worker 可以将状态更新与业务结果
    放在同一个数据库事务中提交。
    """

    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        document_id: int,
        max_attempts: int = 3,
    ) -> ProcessingJob:
        """创建 pending 任务，但暂不提交事务。"""

        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        job = ProcessingJob(
            task_id=str(uuid4()),
            document_id=document_id,
            status="pending",
            attempt_count=0,
            max_attempts=max_attempts,
        )

        self.db.add(job)
        self.db.flush()

        return job

    def get_by_task_id(
        self,
        task_id: str,
    ) -> ProcessingJob | None:
        """根据公开任务 ID 查询数据库中的业务状态。"""

        return self.db.scalar(
            select(ProcessingJob).where(
                ProcessingJob.task_id == task_id
            )
        )

    def claim_job(
        self,
        task_id: str,
    ) -> ProcessingJob | None:
        """原子认领任务，并创建十分钟的执行租约。"""

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "pending",
                ProcessingJob.attempt_count
                < ProcessingJob.max_attempts,
            )
            .values(
                status="processing",
                attempt_count=ProcessingJob.attempt_count + 1,
                started_at=func.now(),
                finished_at=None,
                error_type=None,
                error_message=None,

                # 使用 PostgreSQL 时间，避免 Worker 本地时钟不一致。
                lease_expires_at=func.now()
                + text("INTERVAL '10 minutes'"),
            )
            .returning(ProcessingJob.id)
        )

        job_id = self.db.scalar(statement)

        if job_id is None:
            return None

        return self.db.get(ProcessingJob, job_id)

    def mark_completed(
        self,
        task_id: str,
        attempt_count: int,
    ) -> bool:
        """
        将当前有效的处理尝试标记为 completed。

        必须同时检查 task_id、processing 状态、
        attempt_count，防止旧 Worker 完成新任务。
        """

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.attempt_count == attempt_count,
                ProcessingJob.lease_expires_at > func.now(),
            )
            .values(
                status="completed",
                finished_at=func.now(),
                error_type=None,
                error_message=None,
                lease_expires_at=None,
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None

    def mark_failed(
        self,
        task_id: str,
        attempt_count: int,
        error_type: str,
        error_message: str,
    ) -> bool:
        """仅允许当前执行尝试记录失败。"""

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.attempt_count == attempt_count,
            )
            .values(
                status="failed",
                finished_at=func.now(),
                error_type=error_type[:100],
                error_message=error_message[:2000],
                lease_expires_at=None,
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None
    
    
    def prepare_retry(
        self,
        task_id: str,
        attempt_count: int,
        error_type: str,
        error_message: str,
        delay_seconds: int = 2,
    ) -> bool:
        """安排任务重试，保存下次允许派发的数据库时间。"""
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.attempt_count == attempt_count,
                ProcessingJob.attempt_count < ProcessingJob.max_attempts,
                # 只允许仍持有有效租约的 Worker 安排重试。
                ProcessingJob.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                status="pending",
                started_at=None,
                finished_at=None,
                lease_expires_at=None,
                error_type=error_type[:100],
                error_message=error_message[:2000],

                # 由 PostgreSQL 计算计划执行时间，避免 Worker 时钟偏差。
                next_dispatch_at=func.clock_timestamp()
                + func.make_interval(0, 0, 0, 0, 0, 0, delay_seconds),
            )
            .returning(ProcessingJob.id)
        )

        
        return self.db.scalar(statement) is not None
    
    def renew_lease(
        self,
        task_id: str,
        attempt_count: int,
    ) -> bool:
        #仅允许当前有效的执行尝试续租。

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.attempt_count == attempt_count,
                ProcessingJob.lease_expires_at > func.clock_timestamp(),
            )
            .values(
                lease_expires_at=func.clock_timestamp()
                + text("INTERVAL '10 minutes'")
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None
    
    def recover_expired_job(
        self,
        task_id: str,
    ) -> bool:
        """将租约过期且仍有剩余次数的任务恢复为 pending。"""

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.lease_expires_at.is_not(None),
                ProcessingJob.lease_expires_at
                < func.clock_timestamp(),
                ProcessingJob.attempt_count
                < ProcessingJob.max_attempts,
            )
            .values(
                status="pending",
                lease_expires_at=None,
                started_at=None,
                finished_at=None,
                next_dispatch_at=None,
                error_type="LeaseExpired",
                error_message="Worker lease expired",
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None


    def fail_expired_job(self, task_id: str) -> bool:
        """将租约过期且执行次数耗尽的任务标记为最终失败。"""

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "processing",
                ProcessingJob.lease_expires_at < func.now(),
                ProcessingJob.attempt_count
                >= ProcessingJob.max_attempts,
            )
            .values(
                status="failed",
                lease_expires_at=None,
                finished_at=func.now(),
                error_type="LeaseExpired",
                error_message="Worker lease expired; attempts exhausted",
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None

    
    def list_recovery_candidates(
        self,
        limit: int = 100,
    ) -> list[ProcessingJob]:
        """查询可派发的 pending 任务及租约过期的 processing 任务。"""

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        statement = (
            select(ProcessingJob)
            .where(
                or_(
                    # 第一类：已经到达派发时间的待处理任务。
                    and_(
                        ProcessingJob.status == "pending",
                        ProcessingJob.attempt_count
                        < ProcessingJob.max_attempts,
                        or_(
                            ProcessingJob.next_dispatch_at.is_(None),
                            ProcessingJob.next_dispatch_at <= func.now(),
                        ),
                    ),

                    # 第二类：租约已经过期的执行中任务。
                    # 即使次数耗尽，也必须扫描出来执行最终失败处理。
                    and_(
                        ProcessingJob.status == "processing",
                        ProcessingJob.lease_expires_at.is_not(None),
                        ProcessingJob.lease_expires_at < func.now(),
                    ),
                )
            )
            .order_by(
                ProcessingJob.created_at,
                ProcessingJob.id,
            )
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())



    def reserve_dispatch(
        self,
        task_id: str,
        interval_seconds: int = 30,
    ) -> bool:
        """原子预留任务派发资格，并设置下一次允许派发的时间。"""

        if interval_seconds < 1:
            raise ValueError(
                "interval_seconds must be >= 1"
            )

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.task_id == task_id,
                ProcessingJob.status == "pending",
                ProcessingJob.attempt_count
                < ProcessingJob.max_attempts,

                # 未设置时间限制，或已达到最早派发时间。
                (
                    ProcessingJob.next_dispatch_at.is_(None)
                    | (
                        ProcessingJob.next_dispatch_at
                        <= func.now()
                    )
                ),
            )
            .values(
                # 记录此次获得派发资格的时间。
                last_dispatched_at=func.now(),

                # 设置预留窗口，避免其他调度器立即重复派发。
                next_dispatch_at=func.now()
                + text(
                    f"INTERVAL '{interval_seconds} seconds'"
                ),
            )
            .returning(ProcessingJob.id)
        )

        return self.db.scalar(statement) is not None
    
    def create_retry_job(
        self,
        task_id: str,
    ) -> ProcessingJob | None:
        """锁定关联文档后，为失败任务创建新的处理任务。"""

        # 第一次查询仅用于定位 document_id，不锁定 Job。
        original = self.get_by_task_id(task_id)

        if original is None:
            return None

        document = self.db.scalar(
            select(Document)
            .where(Document.id == original.document_id)
            .with_for_update()
        )

        if document is None:
            return None

        # 获得文档锁后重新查询状态，避免使用过期判断。
        self.db.expire(original)

        if original.status != "failed":
            return None

        new_job = ProcessingJob(
            document_id=document.id,
            max_attempts=original.max_attempts,
            status="pending",
            attempt_count=0,
        )

        self.db.add(new_job)
        self.db.flush()

        return new_job
