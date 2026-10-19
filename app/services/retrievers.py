"""定义统一检索协议，并适配已有论文检索服务。"""

from typing import Protocol, runtime_checkable

from app.schemas.search import SearchResult

@runtime_checkable
class Retriever(Protocol):
    """统一检索器协议，支持运行时结构检查。"""

    name: str

    def retrieve(
        self,
        query: str,
        *,
        document_id: int | None = None,
        title: str | None = None,
        doi: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """返回标准化检索结果。"""


class KeywordRetriever:
    """适配已有 PostgreSQL Chunk 检索实现。"""

    def __init__(self, search_service, mode: str = "literal"):
        if mode not in {"literal", "fts"}:
            raise ValueError("unsupported keyword mode")

        self.service = search_service
        self.mode = mode
        self.name = f"keyword_{mode}"

    def retrieve(
        self,
        query: str,
        *,
        document_id: int | None = None,
        limit: int = 20,
        title: str | None = None,
        doi: str | None = None,
    ) -> list[SearchResult]:
        """执行正文检索，拒绝不支持的元数据条件。"""

        if title is not None or doi is not None:
            raise ValueError(
                "keyword retriever does not support title or doi filters"
            )

        return self.service.search_chunks(
            query,
            mode=self.mode,
            document_id=document_id,
            limit=limit,
        )


class MetadataRetriever:
    """适配已有论文元数据检索实现。"""

    name = "metadata"

    def __init__(self, search_service):
        self.service = search_service

    def retrieve(
        self,
        query: str,
        *,
        document_id: int | None = None,
        limit: int = 20,
        title: str | None = None,
        doi: str | None = None,
    ) -> list[SearchResult]:
        """执行元数据检索，保持结构化过滤条件。"""

        normalized_title = title

        if normalized_title is None and query.strip():
            normalized_title = query.strip()

        if (
            document_id is None
            and not normalized_title
            and doi is None
        ):
            raise ValueError(
                "metadata retriever requires document_id, title or doi"
            )

        # 兼容 Day 10 之前已有的调用测试。
        if doi is None and title is None:
            if document_id is not None:
                return self.service.search_papers(
                    document_id=document_id,
                    limit=limit,
                )

            return self.service.search_papers(
                title=normalized_title,
                limit=limit,
            )

        return self.service.search_papers(
            document_id=document_id,
            title=normalized_title,
            doi=doi,
            limit=limit,
        )