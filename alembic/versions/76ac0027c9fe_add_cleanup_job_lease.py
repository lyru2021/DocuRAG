"""add cleanup job lease

Revision ID: 76ac0027c9fe
Revises: f4e6933cfbd7
Create Date: 2026-10-15 19:31:05.140939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76ac0027c9fe'
down_revision: Union[str, Sequence[str], None] = 'f4e6933cfbd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增文件清理租约字段，并允许 processing 状态。"""

    op.add_column(
        "file_cleanup_jobs",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "file_cleanup_jobs",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 删除原有状态约束。
    op.drop_constraint(
        "ck_file_cleanup_jobs_status",
        "file_cleanup_jobs",
        type_="check",
    )

    # 新状态机：pending → processing → completed。
    op.create_check_constraint(
        "ck_file_cleanup_jobs_status",
        "file_cleanup_jobs",
        "status IN ('pending', 'processing', 'completed')",
    )


def downgrade() -> None:
    """恢复原有状态约束并删除租约字段。"""

    # 降级前不能保留旧模型不支持的 processing 状态。
    op.execute(
        """
        UPDATE file_cleanup_jobs
        SET status = 'pending'
        WHERE status = 'processing'
        """
    )

    op.drop_constraint(
        "ck_file_cleanup_jobs_status",
        "file_cleanup_jobs",
        type_="check",
    )

    op.create_check_constraint(
        "ck_file_cleanup_jobs_status",
        "file_cleanup_jobs",
        "status IN ('pending', 'completed')",
    )

    op.drop_column(
        "file_cleanup_jobs",
        "lease_expires_at",
    )

    op.drop_column(
        "file_cleanup_jobs",
        "started_at",
    )
