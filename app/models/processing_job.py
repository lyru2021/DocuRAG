"""
定义论文异步处理任务的数据库模型及字段约束。
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessingJob(Base):
    """论文异步处理任务表。
    职责：
    1. 记录每一次论文处理任务。
    2. 持久化任务执行状态，供 API 查询。
    3. 记录失败原因及重试次数。
    4. 为 Worker 的幂等处理提供数据库依据。
    """   
    __tablename__ = "processing_jobs"

    # 数据库层约束：防止非法状态和重试次数写入。
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'processing', 'completed', 'failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_processing_jobs_attempt_count",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="ck_processing_jobs_max_attempts",
        ),
        CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_processing_jobs_attempt_limit",
        ),
        Index(
            "uq_processing_jobs_one_active_per_document",
            "document_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending', 'processing')"
            ),
        ),
    )

    # 数据库内部主键
    id: Mapped[int] = mapped_column(primary_key=True)

    # 对外暴露的任务标识，使用 UUID 避免简单递增 ID。
    task_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )

    # 关联待处理的论文。
    # 删除 Document 时，关联的处理任务也会被删除。
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 当前业务状态：
    # pending    等待处理
    # processing Worker 正在处理
    # completed  处理结果已成功持久化
    # failed     任务失败
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )

    # 已经开始执行的次数。
    # 只有真正认领并开始一次任务尝试时才递增。
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )

    # 最大执行次数
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="3",
    )

    # 失败类型，例如：
    # InvalidPDFError（永久性失败）
    # OperationalError（可能是暂时性失败）
    error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 保存简要错误信息。
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 创建时间：由 PostgreSQL 生成。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Worker 开始执行任务的时间。
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 任务最终完成或失败的时间。
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 当前处理尝试的租约到期时间。
    # 只有 processing 任务需要租约。
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

        # 最早允许重新派发任务的时间；NULL 表示没有额外时间限制。
    next_dispatch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 最近一次尝试向消息队列派发任务的时间。
    last_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
