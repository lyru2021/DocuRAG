"""基于 PostgreSQL 的论文元数据过滤服务。"""

from sqlalchemy import select, func, Select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.paper import PaperMetadata


class PaperSearchRepository:
    """按论文元数据筛选并稳定排序。"""

    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        *,
        document_id: int | None = None,
        title: str | None = None,
        author: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        limit: int = 20,
    ) -> list[Document]:
        """执行组合过滤，返回真实文档记录。"""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        statement = select(Document)

        # 仅在请求 DOI 时关联论文元数据表，避免影响普通检索。
        if doi is not None:
            doi = doi.strip()

            if not doi:
                raise ValueError("doi must not be empty")

            statement = statement.join(
                PaperMetadata,
                PaperMetadata.document_id == Document.id,
            ).where(
                func.lower(PaperMetadata.doi) == doi.lower()
            )

        if document_id is not None:
            statement = statement.where(
                Document.id == document_id
            )

        if title is not None:
            title = title.strip()

            if title:
                statement = statement.where(
                    Document.title.ilike(
                        f"%{self._escape_like(title)}%",
                        escape="\\",
                    )
                )

        if author is not None:
            author = author.strip()

            if author:
                statement = statement.where(
                    Document.authors.ilike(
                        f"%{self._escape_like(author)}%",
                        escape="\\",
                    )
                )

        if year is not None:
            statement = statement.where(
                Document.publication_year == year
            )

        statement = (
            statement
            .order_by(Document.id.asc())
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())

    @staticmethod
    def _escape_like(value: str) -> str:
        """将用户输入作为普通文本，而非 SQL LIKE 通配符。"""

        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )