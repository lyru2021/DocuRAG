"""add paper full text search indexes

Revision ID: e43972c76294
Revises: 6262d89f1df6
Create Date: 2026-10-16 15:34:46.996163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e43972c76294'
down_revision: Union[str, Sequence[str], None] = '6262d89f1df6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


"""add paper full text search indexes"""


def upgrade() -> None:
    """创建论文全文和子串检索索引。"""

    # 三元组 GIN 索引依赖 PostgreSQL 的 pg_trgm 扩展。
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE INDEX ix_chunks_content_fts
        ON chunks
        USING GIN (
            to_tsvector('simple'::regconfig, content)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_chunks_content_trgm
        ON chunks
        USING GIN (content gin_trgm_ops)
        """
    )

    op.execute(
        """
        CREATE INDEX ix_documents_title_trgm
        ON documents
        USING GIN (title gin_trgm_ops)
        """
    )


def downgrade() -> None:
    """移除本次新增的检索索引。"""

    op.drop_index(
        "ix_documents_title_trgm",
        table_name="documents",
    )

    op.drop_index(
        "ix_chunks_content_trgm",
        table_name="chunks",
    )

    op.drop_index(
        "ix_chunks_content_fts",
        table_name="chunks",
    )

    # 不删除 pg_trgm 扩展，避免影响其他对象。