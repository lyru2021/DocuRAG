"""使用 PostgreSQL 全文索引及原文匹配检索论文 Chunk。"""

from dataclasses import dataclass

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document


@dataclass(frozen=True)
class ChunkSearchHit:
    """保留真实证据位置与检索来源的 Chunk 命中结果。"""

    document_id: int
    chunk_id: int
    page_start: int | None
    page_end: int | None
    content: str
    score: float
    retrieval_source: str


class ChunkSearchRepository:
    """封装英文全文检索与原文关键词匹配。"""

    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        query: str,
        *,
        mode: str = "literal",
        document_id: int | None = None,
        limit: int = 20,
    ) -> list[ChunkSearchHit]:
        """按指定检索模式查询已解析文档的 Chunk。"""

        query = query.strip()

        if not query:
            raise ValueError("query must not be empty")

        if mode not in {"literal", "fts"}:
            raise ValueError("unsupported search mode")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        statement = (
            select(Chunk)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.parse_status == "parsed")
        )

        if document_id is not None:
            statement = statement.where(
                Chunk.document_id == document_id
            )

        if mode == "fts":
            vector = func.to_tsvector(
                "simple",
                Chunk.content,
            )
            tsquery = func.websearch_to_tsquery(
                "simple",
                query,
            )
            score = func.ts_rank(vector, tsquery)

            statement = (
                statement
                .where(vector.op("@@")(tsquery))
                .add_columns(score.label("score"))
                .order_by(
                    score.desc(),
                    Chunk.document_id.asc(),
                    Chunk.chunk_index.asc(),
                    Chunk.id.asc(),
                )
            )

        else:
            escaped = (
                query.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )

            statement = (
                statement
                .where(
                    Chunk.content.ilike(
                        f"%{escaped}%",
                        escape="\\",
                    )
                )
                .add_columns(
                    cast(1.0, Float).label("score")
                )
                .order_by(
                    Chunk.document_id.asc(),
                    Chunk.chunk_index.asc(),
                    Chunk.id.asc(),
                )
            )

        statement = statement.limit(limit)

        return [
            ChunkSearchHit(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content=chunk.content,
                score=float(score_value),
                retrieval_source=(
                    "postgres_fts"
                    if mode == "fts"
                    else "postgres_literal"
                ),
            )
            for chunk, score_value in self.db.execute(statement)
        ]