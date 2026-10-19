"""在真实 PostgreSQL 上执行两种切分配置的关键词检索。"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select, Float
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document
from app.models.retrieval_experiment_chunk import RetrievalExperimentChunk


@dataclass(frozen=True)
class ExperimentHit:
    """统一表示一个带有原文证据区间的实验检索结果。"""

    experiment_id: str
    document_id: int
    chunk_index: int
    start_char: int
    end_char: int
    page_start: int | None
    page_end: int | None
    content: str
    score: float
    retrieval_source: str


class ExperimentPostgresRetriever:
    """隔离两套实验 Chunk，并复用相同的检索算法。"""

    SUPPORTED = {
        "chunk300_overlap50": Chunk,
        "chunk500_overlap50": RetrievalExperimentChunk,
    }

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _escape_like(value: str) -> str:
        """避免用户输入中的百分号和下划线变成通配符。"""

        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    def search(
        self,
        *,
        experiment_id: str,
        query: str,
        mode: Literal["literal", "fts"],
        document_ids: list[int],
        limit: int = 5,
    ) -> list[ExperimentHit]:
        """按指定实验配置执行真实 PostgreSQL 查询。"""

        if experiment_id not in self.SUPPORTED:
            raise ValueError("unsupported experiment")

        if mode not in {"literal", "fts"}:
            raise ValueError("unsupported mode")

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        query = query.strip()

        if not query:
            raise ValueError("query must not be empty")

        if not document_ids:
            raise ValueError("document_ids must not be empty")

        model = self.SUPPORTED[experiment_id]

        statement = (
            select(model)
            .join(Document, model.document_id == Document.id)
            .where(
                model.document_id.in_(document_ids),
                Document.parse_status == "parsed",
            )
        )

        if experiment_id == "chunk500_overlap50":
            statement = statement.where(
                model.experiment_id == experiment_id
            )

        if mode == "literal":
            statement = (
                statement
                .where(
                    model.content.ilike(
                        f"%{self._escape_like(query)}%",
                        escape="\\",
                    )
                )
                .add_columns(
                    func.cast(1.0, Float).label("rank_score")
                )
                .order_by(
                    model.document_id.asc(),
                    model.chunk_index.asc(),
                )
            )
        else:
            # 同一条 SQL 中完成 FTS 匹配、排序和分数计算。
            vector = func.to_tsvector("simple", model.content)
            tsquery = func.websearch_to_tsquery("simple", query)
            rank_score = func.ts_rank(vector, tsquery)

            statement = (
                statement
                .where(vector.op("@@")(tsquery))
                .add_columns(rank_score.label("rank_score"))
                .order_by(
                    rank_score.desc(),
                    model.document_id.asc(),
                    model.chunk_index.asc(),
                )
            )

        statement = statement.limit(limit)

        # 每个结果同时包含 ORM Chunk 和 PostgreSQL 计算的分数。
        rows = self.db.execute(statement).all()

        return [
            ExperimentHit(
                experiment_id=experiment_id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content=chunk.content,
                score=float(rank_score),
                retrieval_source=f"postgres_{mode}",
            )
            for chunk, rank_score in rows
        ]