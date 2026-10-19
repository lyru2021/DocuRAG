"""add retrieval experiment chunks

Revision ID: ef77a147eea7
Revises: e43972c76294
Create Date: 2026-10-19 15:02:12.468858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef77a147eea7'
down_revision: Union[str, Sequence[str], None] = 'e43972c76294'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建独立实验 Chunk 表及对应检索索引。"""

    op.create_table("retrieval_experiment_chunks", 
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "document_id", "chunk_index", name="uq_retrieval_experiment_chunk_position"),
    )

    # 英文全文检索，使用与现有 Chunk 相同的 simple 配置。
    op.create_index("ix_retrieval_exp_chunks_fts", "retrieval_experiment_chunks",[sa.literal_column("to_tsvector('simple'::regconfig, content)")],postgresql_using="gin")

    # 中文等文本使用字面匹配；trigram 索引用于辅助加速。
    op.create_index("ix_retrieval_exp_chunks_trgm","retrieval_experiment_chunks",["content"],postgresql_using="gin",postgresql_ops={"content": "gin_trgm_ops"})

    # 实验 ID + 文档 ID 是后续实验查询的常用过滤条件。
    op.create_index("ix_retrieval_exp_chunks_experiment_document","retrieval_experiment_chunks",["experiment_id", "document_id"])


def downgrade() -> None:
    """删除实验表，不触碰现有业务检索索引。"""

    op.drop_index("ix_retrieval_exp_chunks_experiment_document", table_name="retrieval_experiment_chunks")

    op.drop_index("ix_retrieval_exp_chunks_trgm",table_name="retrieval_experiment_chunks")

    op.drop_index("ix_retrieval_exp_chunks_fts",table_name="retrieval_experiment_chunks")

    op.drop_table("retrieval_experiment_chunks")
