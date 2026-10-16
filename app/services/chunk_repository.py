"""chunk 持久化服务。

管理文档 Chunk 的切分、页面映射和数据库持久化。
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import (
    Chunk,
    Document,
    DocumentPage,
)
from app.services.page_mapper import find_chunk_page_range
from app.services.text_chunker import split_text


class ChunkRepository:
    """文档分块的持久化入口。

    负责把解析后的全文切成可检索片段，并把每个片段映射回 PDF 页码范围。
    """

    def __init__(self, db: Session):
        self.db = db

    def replace_document_chunks(
        self,
        document_id: int,
        chunk_size: int = 300,
        overlap: int = 50,
        *,
        auto_commit: bool = True,
    ) -> list[Chunk]:
        """
        Replace document chunks in one transaction.

        Also map chunk character offsets to PDF pages.

        Args:
            document_id: 需要重新分块的文档主键。
            chunk_size: 单个 chunk 的最大字符长度。
            overlap: 相邻 chunk 之间复用的字符数。

        Returns:
            list[Chunk]: 本次新建并提交的 chunk 对象列表。

        Raises:
            ValueError: 文档不存在、没有可分块文本，或分块结果为空。
            Exception: 数据库写入失败时回滚当前 Session 后继续抛出原异常。
        """

        try:
            # 1. Load the document.
            document = self.db.get(Document, document_id)

            if document is None:
                raise ValueError("Document not found")

            if not document.extracted_text:
                raise ValueError(
                    "Document has no extracted text"
                )

            # 2. Split extracted text into chunks.
            parts = split_text(
                document.extracted_text,
                chunk_size=chunk_size,
                overlap=overlap,
            )

            if not parts:
                raise ValueError("No chunks generated")

            # 3. Load PDF page mappings.
            # TXT documents normally have no page records.
            pages = list(
                self.db.scalars(
                    select(DocumentPage)
                    .where(
                        DocumentPage.document_id == document_id
                    )
                    .order_by(DocumentPage.page_number)
                ).all()
            )

            # 4. Remove previous chunks.
            self.db.execute(
                delete(Chunk).where(
                    Chunk.document_id == document_id
                )
            )

            # 5. Build new chunks with page ranges.
            # 页码范围来自字符区间交集，而不是重新解析 chunk 内容，避免重复文本导致误判。
            chunks = []

            for part in parts:
                page_start, page_end = find_chunk_page_range(
                    part.start_char,
                    part.end_char,
                    pages,
                )

                chunk = Chunk(
                    document_id=document_id,
                    chunk_index=part.chunk_index,
                    content=part.content,
                    start_char=part.start_char,
                    end_char=part.end_char,
                    page_start=page_start,
                    page_end=page_end,
                )

                chunks.append(chunk)

            # 6. Save all chunks.
            self.db.add_all(chunks)

            if auto_commit:
                self.db.commit()
            else:
                # 只将 SQL 发送到数据库，不提交事务。
                # 后续 Worker 可以统一提交 Chunk 与任务状态。
                self.db.flush()

            return chunks

        except Exception:
            if auto_commit:
                self.db.rollback()
            # auto_commit=False 时，事务归调用方管理。
            raise

    def list_document_chunks(
        self,
        document_id: int,
    ) -> list[Chunk]:
        """按 chunk_index 返回某个文档的全部分块。

        Args:
            document_id: `documents.id` 主键。

        Returns:
            list[Chunk]: 按原文顺序排列的 chunk 列表。
        """

        statement = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )

        return list(
            self.db.scalars(statement).all()
        )
