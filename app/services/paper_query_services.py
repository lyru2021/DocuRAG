"""论文查询聚合服务。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document, DocumentPage
from app.models.paper import PaperMetadata
from app.services.evidence_validator import validate_evidence


class PaperQueryService:
    """论文查询聚合服务。

    API 层通过该服务读取文档、页面、chunk 和 evidence，避免路由函数直接拼 SQL。
    """

    def __init__(self, db: Session):
        self.db = db

    def get_document(self, document_id: int) -> Document | None:
        """按文档主键读取论文对应的文档记录。"""

        return self.db.get(Document, document_id)

    def get_metadata(self, document_id: int) -> PaperMetadata | None:
        """读取文档的一对一论文元数据。"""

        return self.db.scalar(
            select(PaperMetadata).where(
                PaperMetadata.document_id == document_id
            )
        )

    def get_pages(self, document_id: int) -> list[DocumentPage]:
        """按页码顺序读取 PDF 页面映射。"""

        return list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            ).all()
        )

    def get_chunks(self, document_id: int) -> list[Chunk]:
        """按 chunk_index 顺序读取文档分块。"""

        return list(
            self.db.scalars(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.chunk_index)
            ).all()
        )

    def get_evidence(
        self,
        document_id: int,
        chunk_id: int,
    ) -> dict | None:
        """返回 chunk 证据及其校验结果。

        Args:
            document_id: 文档主键。
            chunk_id: chunk 主键。

        Returns:
            dict | None: chunk 不存在、文档不存在或二者不匹配时返回 None。
        """

        document = self.get_document(document_id)

        if document is None:
            return None

        chunk = self.db.get(Chunk, chunk_id)

        if chunk is None or chunk.document_id != document_id:
            return None

        pages = self.get_pages(document_id)

        validation = validate_evidence(
            full_text=document.extracted_text or "",
            chunk=chunk,
            pages=pages,
        )

        return {
            "document_id": document.id,
            "chunk_id": chunk.id,
            "filename": document.filename,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "quote": chunk.content,
            "verified": validation.verified,
            "text_verified": validation.text_verified,
            "pages_verified": validation.pages_verified,
        }
