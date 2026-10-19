"""保存独立切分配置的实验 Chunk，不修改业务 Chunk。"""

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RetrievalExperimentChunk(Base):
    """保存指定实验版本的原文 Chunk 和真实证据区间。"""

    __tablename__ = "retrieval_experiment_chunks"

    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "document_id",
            "chunk_index",
            name="uq_retrieval_experiment_chunk_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    experiment_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    page_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    page_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )