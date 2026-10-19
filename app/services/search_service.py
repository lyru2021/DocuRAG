"""统一协调论文元数据检索、Chunk 检索及章节定位。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.paper import PaperSection
from app.schemas.search import SearchResult
from app.services.chunk_search_repository import ChunkSearchRepository
from app.services.paper_search_repository import PaperSearchRepository


class SearchService:
    """为 API 和内部工具提供统一检索入口。"""

    def __init__(self, db: Session):
        self.db = db
        self.papers = PaperSearchRepository(db)
        self.chunks = ChunkSearchRepository(db)

    def search_papers(
        self,
        *,
        document_id: int | None = None,
        title: str | None = None,
        author: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """按元数据查找论文。"""

        documents = self.papers.search(
            document_id=document_id,
            title=title,
            author=author,
            year=year,
            doi=doi,
            limit=limit,
        )

        return [
            SearchResult(
                document_id=document.id,
                title=document.title,
                retrieval_source="metadata",
            )
            for document in documents
        ]

    def search_chunks(
        self,
        query: str,
        *,
        mode: str = "literal",
        document_id: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """检索原文 Chunk，并补充论文标题。"""

        hits = self.chunks.search(
            query,
            mode=mode,
            document_id=document_id,
            limit=limit,
        )

        if not hits:
            return []

        document_ids = {hit.document_id for hit in hits}

        documents = self.db.scalars(
            select(Document).where(
                Document.id.in_(document_ids)
            )
        ).all()

        titles = {
            document.id: document.title
            for document in documents
        }

        return [
            SearchResult(
                document_id=hit.document_id,
                title=titles[hit.document_id],
                chunk_id=hit.chunk_id,
                page_start=hit.page_start,
                page_end=hit.page_end,
                content=hit.content,
                score=hit.score,
                retrieval_source=hit.retrieval_source,
            )
            for hit in hits
        ]

    def get_paper_section(
        self,
        document_id: int,
        section_id: int,
    ) -> SearchResult | None:
        """定位论文中的已记录章节候选。"""

        section = self.db.scalar(
            select(PaperSection).where(
                PaperSection.id == section_id,
                PaperSection.document_id == document_id,
            )
        )

        if section is None:
            return None

        document = self.db.get(Document, document_id)

        if document is None:
            return None

        return SearchResult(
            document_id=document.id,
            title=document.title,
            page_start=section.page_number,
            page_end=section.page_number,
            content=None,
            score=None,
            retrieval_source="paper_section",
            section_id=section.id,
            section_heading=section.heading,
            verification_status=section.verification_status,
        )