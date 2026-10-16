"""记录需要异步清理的本地文件及其执行状态。"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FileCleanupJob(Base):
    """持久化文件删除请求，支持失败后重新执行。"""

    __tablename__ = "file_cleanup_jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed')",
            name="ck_file_cleanup_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 仅记录文件标识，不关联 Document 外键。
    # Document 删除后，清理记录仍必须存在。
    file_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )